"""Local chat with your own trained LucidAI v4 checkpoint."""
import argparse
import json
import sys
from pathlib import Path
import torch
from config import ModelConfig
from model import LucidAI
from tokenizer import SPECIAL, encode_messages, encode_text, fingerprint, load_tokenizer
from train import load_checkpoint, resolve_device

SYSTEM = "You are LucidAI. Write clear, natural English. Answer the user's question directly. Explain when helpful, and say when you are unsure."


def build_prompt(tokenizer, history, question, context, reserve, system=""):
    base = [{"role": "system", "content": system}] if system else []
    turns = list(history)
    while True:
        messages = base + turns + [{"role": "user", "content": question}]
        ids, _ = encode_messages(tokenizer, messages)
        ids.append(tokenizer.token_to_id("<|assistant|>"))
        if len(ids) + reserve <= context:
            return ids
        if len(turns) >= 2:
            turns = turns[2:]
        else:
            raise ValueError("Your message is too long for this model. Shorten it or reduce --max-new-tokens.")


class ChatSession:
    def __init__(self, checkpoint, device="auto"):
        path = Path(checkpoint)
        saved = load_checkpoint(path)
        self.device = resolve_device(device)
        tokenizer_path = path.parent / "tokenizer.json"
        if fingerprint(tokenizer_path) != saved["tokenizer_sha256"]:
            raise ValueError("Checkpoint tokenizer does not match its saved fingerprint.")
        self.tokenizer = load_tokenizer(tokenizer_path)
        self.model = LucidAI(ModelConfig(**saved["config"])).to(self.device)
        self.model.load_state_dict(saved["model"])
        self.model.eval()
        self.stage, self.step = saved["stage"], saved["step"]
        self.history = []

    def answer(self, question, max_new_tokens=160, temperature=0.7, top_p=0.9, system=""):
        if not question.strip():
            raise ValueError("Please enter a message.")
        if max_new_tokens < 1:
            raise ValueError("max_new_tokens must be positive.")
        ids = build_prompt(self.tokenizer, self.history, question,
                           self.model.config.context_length, max_new_tokens, system)
        eos = self.tokenizer.token_to_id("<|eos|>")
        banned = [self.tokenizer.token_to_id(t) for t in SPECIAL if t != "<|eos|>"]
        generated = self.model.generate(torch.tensor([ids], device=self.device),
            max_new_tokens=max_new_tokens, temperature=temperature, top_p=top_p,
            stop_ids=(eos,), banned_ids=banned)[0, len(ids):].tolist()
        ended = bool(generated and generated[-1] == eos)
        text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        if text:
            self.history.extend([{"role": "user", "content": question},
                                 {"role": "assistant", "content": text}])
        return text, ended


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="checkpoints/sft/best.pt")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda", "directml"], default="auto")
    parser.add_argument("--prompt")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--system", default="", help="Use only if your SFT data included system messages.")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    if not Path(args.checkpoint).is_file():
        parser.error(f"Checkpoint not found: {args.checkpoint}. Train an SFT model or supply --checkpoint.")
    session = ChatSession(args.checkpoint, args.device)
    print(f"LucidAI v4 | {session.stage} checkpoint, step {session.step} | {session.device}")
    if session.stage != "sft":
        print("This is a base language model; instruction training is still needed.")
    print("Commands: /new, /save <file.json>, /quit")
    while True:
        try:
            question = args.prompt if args.prompt is not None else input("\nYou: ").strip()
            if args.prompt is None and question == "/quit":
                break
            if args.prompt is None and question == "/new":
                session.history.clear()
                print("Started a new conversation.")
                continue
            if args.prompt is None and question.startswith("/save "):
                path = Path(question[6:].strip())
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(session.history, stream, ensure_ascii=False, indent=2)
                print(f"Saved {path.resolve()}")
                continue
            answer, ended = session.answer(question, args.max_new_tokens, args.temperature, args.top_p, args.system)
            print(f"\nLucidAI: {answer or '[No answer generated]'}")
            if not ended:
                print("[Response reached the token limit.]")
        except (EOFError, KeyboardInterrupt):
            break
        except (ValueError, OSError) as error:
            print(f"Error: {error}")
        if args.prompt is not None:
            break


if __name__ == "__main__":
    main()
