import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import sqlite3
import unittest
from unittest.mock import patch

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ModelConfig
from model import LucidAI
from tokenizer import encode_messages, train_tokenizer
from prepare import split_for, digest, valid_messages
from chat import build_prompt, ChatSession
from data import Conversations
import prepare
import train


class ModelTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(2)
        torch.manual_seed(7)
        self.model = LucidAI(ModelConfig(vocab_size=80, context_length=32,
            d_model=32, n_layers=2, n_heads=4, n_kv_heads=2, hidden_dim=64)).eval()

    def test_cached_logits_match_full_sequence(self):
        ids = torch.randint(0, 80, (1, 9))
        with torch.no_grad():
            full, _, _ = self.model(ids)
            _, _, cache = self.model(ids[:, :5], use_cache=True)
            suffix, _, _ = self.model(ids[:, 5:], past=cache, use_cache=True)
        torch.testing.assert_close(suffix, full[:, 5:], atol=1e-6, rtol=1e-5)

    def test_future_tokens_cannot_change_past_logits(self):
        ids = torch.randint(0, 80, (1, 9))
        changed = ids.clone()
        changed[:, 5:] = 4
        torch.testing.assert_close(self.model(ids)[0][:, :5], self.model(changed)[0][:, :5])

    def test_masked_loss_and_checkpointed_backward(self):
        self.model.train()
        self.model.gradient_checkpointing = True
        ids = torch.randint(0, 80, (2, 8))
        labels = ids.clone()
        labels[:, :4] = -100
        logits, loss, _ = self.model(ids, labels)
        expected = torch.nn.functional.cross_entropy(logits[:, 4:].reshape(-1, 80), labels[:, 4:].reshape(-1))
        torch.testing.assert_close(loss, expected)
        loss.backward()
        self.assertTrue(all(p.grad is not None and torch.isfinite(p.grad).all() for p in self.model.parameters()))

    def test_generation_and_context_limits(self):
        prompt = torch.tensor([[3, 7]])
        a = self.model.generate(prompt, max_new_tokens=3, temperature=0)
        b = self.model.generate(prompt, max_new_tokens=3, temperature=0)
        self.assertTrue(torch.equal(a, b))
        self.assertEqual(a.shape[1], 5)
        with self.assertRaises(ValueError):
            self.model(torch.ones((1, 33), dtype=torch.long))

    def test_prefill_projection_and_invalid_sampling(self):
        ids = torch.tensor([[3, 7, 9]])
        full, _, _ = self.model(ids)
        last, _, cache = self.model(ids, use_cache=True, last_token_only=True)
        torch.testing.assert_close(last, full[:, -1:])
        self.assertEqual(cache[0][0].shape[-2], 3)
        for options in ({"temperature": float("nan")}, {"max_new_tokens": 0},
                        {"banned_ids": range(80)}, {"banned_ids": [-1]}):
            with self.assertRaises(ValueError):
                self.model.generate(ids, **options)


class DataTests(unittest.TestCase):
    def test_prepare_preserves_explicit_partitions(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            docs, chats = root / "docs.jsonl", root / "chats.jsonl"
            documents = [{"text": "A complete document about " + topic + ". " +
                          "This text has enough letters to pass the minimum document quality filter.",
                          "group": topic, "split": split}
                         for topic, split in (("gardens", "train"), ("mountains", "val"))]
            conversations = [{"user": "Tell me about " + topic, "assistant": "Here is an explanation.",
                              "group": topic, "split": split}
                             for topic, split in (("gardens", "train"), ("mountains", "val"))]
            docs.write_text("\n".join(map(json.dumps, documents)), encoding="utf-8")
            chats.write_text("\n".join(map(json.dumps, conversations)), encoding="utf-8")
            with patch.object(sys, "argv", ["prepare.py", "--documents", str(docs), "--chat", str(chats),
                    "--out", str(root / "prepared"), "--vocab-size", "300"]):
                prepare.main()
            with contextlib.closing(sqlite3.connect(root / "prepared/records.sqlite")) as db:
                for split, body in db.execute("SELECT split,body FROM records"):
                    self.assertEqual(split, "train" if "gardens" in body else "val")
            source_tokenizer = root / "prepared/tokenizer.json"
            with patch.object(sys, "argv", ["prepare.py", "--documents", str(docs), "--chat", str(chats),
                    "--out", str(root / "continued-data"), "--tokenizer", str(source_tokenizer)]):
                prepare.main()
            self.assertEqual(source_tokenizer.read_bytes(), (root / "continued-data/tokenizer.json").read_bytes())
            self.assertEqual((root / "prepared/pretrain_train.bin").read_bytes(),
                             (root / "continued-data/pretrain_train.bin").read_bytes())

    def test_normalized_split_and_conversation_validation(self):
        self.assertEqual(split_for(digest("Hello  world")), split_for(digest(" hello WORLD ")))
        with self.assertRaises(ValueError):
            valid_messages({"messages": [{"role": "assistant", "content": "Wrong order"},
                                         {"role": "user", "content": "Hi"}]})

    def test_labels_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            tokenizer = train_tokenizer(["Hello world. How are you? I am well."], Path(directory) / "tokenizer.json", 300)
            messages = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "I am well."}]
            ids, labels = encode_messages(tokenizer, messages)
            boundary = ids.index(tokenizer.token_to_id("<|assistant|>"))
            self.assertTrue(all(x == -100 for x in labels[:boundary + 1]))
            self.assertEqual(labels[-1], tokenizer.token_to_id("<|eos|>"))
            short = build_prompt(tokenizer, [], "Hello", 40, 5)
            trimmed = build_prompt(tokenizer, messages * 20, "Hello", len(short) + 5, 5)
            self.assertEqual(short, trimmed)
            with self.assertRaises(ValueError):
                build_prompt(tokenizer, [], "Hello " * 100, 10, 5)
            path = Path(directory) / "rows.jsonl"
            path.write_text(json.dumps({"ids": ids, "labels": labels}) + "\n")
            data = Conversations(path, 64, tokenizer.token_to_id("<|pad|>"))
            x, y = data.batch(1, np.random.default_rng(0), "cpu")
            self.assertEqual(x[0].tolist(), ids[:-1])
            self.assertEqual(y[0].tolist(), labels[1:])


class PipelineTests(unittest.TestCase):
    def test_prepare_pretrain_resume_sft_chat(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            docs, chats = root / "docs.jsonl", root / "chats.jsonl"
            docs.write_text("\n".join(json.dumps({"text": f"Story number {i}. The children walked to the park and watched the birds. They returned home before sunset and ate dinner together."}) for i in range(100)), encoding="utf-8")
            chats.write_text("\n".join(json.dumps({"user": f"Say hello {i}", "assistant": "Hello!"}) for i in range(100)), encoding="utf-8")
            data, pre, resumed, sft = (root / p for p in ("data", "pre", "resumed", "sft"))
            with patch.object(sys, "argv", ["prepare.py", "--documents", str(docs), "--chat", str(chats),
                "--out", str(data), "--vocab-size", "300", "--validation-fraction", "0.2"]):
                prepare.main()
            common = ["--data", str(data), "--steps", "2", "--batch-size", "1", "--accumulation", "2",
                      "--eval-every", "1", "--eval-batches", "1", "--threads", "2", "--device", "cpu"]
            original_save = train.atomic_save

            def capture(payload, path):
                original_save(payload, path)
                if payload["step"] == 1 and path.name == "latest.pt":
                    original_save(payload, root / "step1.pt")

            with patch.object(sys, "argv", ["train.py", "pretrain", "--preset", "tiny", "--context", "32", "--out", str(pre)] + common), patch.object(train, "atomic_save", capture):
                train.main()
            with patch.object(sys, "argv", ["train.py", "pretrain", "--resume", str(root / "step1.pt"), "--out", str(resumed)] + common):
                train.main()
            first, second = train.load_checkpoint(pre / "latest.pt"), train.load_checkpoint(resumed / "latest.pt")
            self.assertEqual(first["trained_tokens"], 128)
            self.assertEqual(first["trained_tokens"], second["trained_tokens"])
            self.assertEqual(json.loads((resumed / "status.json").read_text())["state"], "completed")
            for key in first["model"]:
                torch.testing.assert_close(first["model"][key], second["model"][key], atol=0, rtol=0)
            # A stop request must save before another update, preserving resume.
            stop = root / "STOP"
            stop.touch()
            continued = root / "continued"
            with patch.object(sys, "argv", ["train.py", "pretrain", "--init", str(pre / "latest.pt"),
                    "--out", str(continued), "--stop-file", str(stop)] + common):
                train.main()
            continued_state = train.load_checkpoint(continued / "latest.pt")
            self.assertEqual(continued_state["step"], 0)
            self.assertEqual(continued_state["trained_tokens"], 0)
            for key, value in continued_state["model"].items():
                torch.testing.assert_close(value, first["model"][key], atol=0, rtol=0)
            paused = root / "paused"
            with patch.object(sys, "argv", ["train.py", "pretrain", "--resume", str(root / "step1.pt"),
                    "--out", str(paused), "--stop-file", str(stop)] + common):
                train.main()
            paused_state = train.load_checkpoint(paused / "latest.pt")
            self.assertEqual(paused_state["step"], 1)
            self.assertEqual(json.loads((paused / "status.json").read_text())["state"], "paused")
            with patch.object(sys, "argv", ["train.py", "pretrain", "--resume", str(paused / "latest.pt"),
                    "--out", str(paused)] + common):
                train.main()
            for key, value in train.load_checkpoint(paused / "latest.pt")["model"].items():
                torch.testing.assert_close(value, first["model"][key], atol=0, rtol=0)
            with patch.object(sys, "argv", ["train.py", "sft", "--init", str(pre / "latest.pt"), "--out", str(sft)] + common):
                train.main()
            session = ChatSession(sft / "latest.pt", "cpu")
            answer, ended = session.answer("Hi", max_new_tokens=4, temperature=0)
            self.assertIsInstance(answer, str)
            self.assertIsInstance(ended, bool)
            # Checkpoint/tokenizer mismatch must fail before generation.
            (sft / "tokenizer.json").write_text("{}")
            with self.assertRaises(ValueError):
                ChatSession(sft / "latest.pt", "cpu")


if __name__ == "__main__":
    unittest.main()
