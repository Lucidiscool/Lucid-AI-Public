"""Bounded memorization diagnostic; never publishes its fitted weights as chat."""
import json
from pathlib import Path
import time
import torch
from backend import resolve_device
from config import ModelConfig
from model import LucidAI
from optim import DirectMLAdamW
from tokenizer import encode_messages, load_tokenizer, SPECIAL
from train import load_checkpoint


def main():
    torch.set_num_threads(4)
    torch.manual_seed(918)
    saved = load_checkpoint("checkpoints/learning-pretrain/best.pt")
    device = resolve_device("directml")
    model = LucidAI(ModelConfig(**saved["config"])).to(device)
    model.load_state_dict(saved["model"])
    tokenizer = load_tokenizer("checkpoints/learning-pretrain/tokenizer.json")
    words = ["maple", "lantern", "river", "button", "garden", "velvet"]
    heldout = ["silver", "basket"]
    def example(word):
        return [{"role": "user", "content": f"The secret word is {word}. Repeat the secret word."},
                {"role": "assistant", "content": word}]
    rows = [encode_messages(tokenizer, example(w)) for w in words]
    length = max(len(ids) for ids, _ in rows)
    ids = torch.full((len(rows), length), tokenizer.token_to_id("<|pad|>"), dtype=torch.long)
    labels = torch.full_like(ids, -100)
    for index, (tokens, targets) in enumerate(rows):
        ids[index, :len(tokens)] = torch.tensor(tokens)
        labels[index, :len(targets)] = torch.tensor(targets)
    x, y = ids[:, :-1].to(device), labels[:, 1:].to(device)
    optimizer = DirectMLAdamW(model.parameters(), lr=1e-4, betas=(.9, .95), weight_decay=0, foreach=False)
    started = time.monotonic()
    losses = []
    for step in range(201):
        model.train()
        _, loss, _ = model(x, y)
        if not torch.isfinite(loss):
            raise FloatingPointError("Diagnostic loss is not finite.")
        if step % 25 == 0:
            losses.append({"step": step, "loss": loss.item()})
            print(losses[-1], flush=True)
        if step == 200:
            break
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True, foreach=False)
        optimizer.step()
    results = []
    for word in words + heldout:
        prompt, _ = encode_messages(tokenizer, example(word)[:1])
        prompt.append(tokenizer.token_to_id("<|assistant|>"))
        result = model.generate(torch.tensor([prompt], device=device), max_new_tokens=12,
            temperature=0, repetition_penalty=1.0, stop_ids=[tokenizer.token_to_id("<|eos|>")],
            banned_ids=[tokenizer.token_to_id(s) for s in SPECIAL if s != "<|eos|>"])
        answer = tokenizer.decode(result[0, len(prompt):].tolist(), skip_special_tokens=True).strip()
        results.append({"word": word, "split": "memorization" if word in words else "unseen_word_same_template",
                        "answer": answer, "correct": answer == word})
    report = {"checkpoint": "checkpoints/learning-pretrain/best.pt", "updates": 200,
              "elapsed_seconds": time.monotonic() - started, "losses": losses, "results": results,
              "note": "Six-example exact-fit diagnostic, not a language/reasoning benchmark. Fitted weights discarded."}
    Path("runs/learning-diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    main()
