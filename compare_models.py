"""Reproducible CPU comparison with shared greedy decoding, separate imports."""
import argparse
import json
from pathlib import Path
import sys
import torch
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
PROMPTS = ["Hello!", "What is your name?", "How are you?", "What is 2 + 3?",
           "What color is the sky on a clear day?", "What is a cat?",
           "Say only the word hello.", "What is 17 + 26?",
           "Lena has a red cup. What color is Lena's cup?",
           "Name two fruits."]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("version", choices=["v3", "v4"])
    parser.add_argument("checkpoint")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(1337)
    checkpoint = Path(args.checkpoint).resolve()
    saved = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if args.version == "v3":
        sys.path.insert(0, str(ROOT.parent / "lucidai_v3"))
        from model import LucidAI
        model = LucidAI()
        tokenizer = Tokenizer.from_file(str(ROOT.parent / "lucidai_v3/tokenizer.json"))
    else:
        from model import LucidAI
        from config import ModelConfig
        model = LucidAI(ModelConfig(**saved["config"]))
        tokenizer = Tokenizer.from_file(str(checkpoint.parent / "tokenizer.json"))
    model.load_state_dict(saved["model"])
    model.eval()
    metadata = {k: v for k, v in saved.items() if k in (
        "step", "best_validation_loss", "best_val_loss", "trained_tokens", "settings", "config")}
    # Read the shared review prompts without importing V4's model into V3.
    review = json.loads((ROOT / "runs/learning-review.json").read_text())
    prompts = PROMPTS + [row["prompt"] for row in review["results"] if row["category"] != "conversation"]
    special = lambda name: tokenizer.token_to_id("<|" + name + "|>")
    results = []
    with torch.no_grad():
        for question in prompts:
            ids = [special("bos"), special("user"), *tokenizer.encode(question).ids,
                   special("eos"), special("assistant")]
            sequence = torch.tensor([ids])
            generated = []
            for _ in range(64):
                logits = model(sequence)[0][:, -1].clone()
                logits[:, [special(t) for t in ("pad", "unk", "bos", "user", "assistant", "system")]] = -float("inf")
                token = logits.argmax(-1).item()
                generated.append(token)
                if token == special("eos"):
                    break
                sequence = torch.cat([sequence, torch.tensor([[token]])], dim=1)
            answer = tokenizer.decode(generated, skip_special_tokens=True).strip()
            results.append({"prompt": question, "answer": answer})
            print(question + "\n" + answer + "\n", flush=True)
    output = {"checkpoint": str(checkpoint), "parameters": sum(p.numel() for p in model.parameters()),
              "metadata": metadata, "decoding": "CPU greedy, no repetition penalty, structural tokens banned, 64 new tokens", "results": results}
    Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
