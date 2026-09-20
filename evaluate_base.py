"""Base-language diagnostics without chat role prompts or instruction tuning."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import torch
from backend import resolve_device
from config import ModelConfig
from data import Corpus
from model import LucidAI
from tokenizer import load_tokenizer, encode_text, SPECIAL, fingerprint
from train import load_checkpoint, evaluate

PROMPTS = ["A robin built a nest in the old tree. One morning,",
           "When water freezes,", "To compare two ideas fairly,", "A paragraph is"]
PAIRS = [("The children are playing outside.", "The children is playing outside."),
         ("She walked home yesterday.", "She walk home yesterday."),
         ("I have an umbrella.", "I have a umbrella."),
         ("There are three books on the table.", "There is three books on the table."),
         ("The dog chased the ball.", "Dog the the chased ball."),
         ("We were tired after the walk.", "We was tired after the walk.")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--data", default="data/base-expanded")
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="directml")
    args = parser.parse_args()
    torch.set_num_threads(4)
    saved = load_checkpoint(args.checkpoint)
    tokenizer_path = Path(args.checkpoint).parent / "tokenizer.json"
    assert fingerprint(tokenizer_path) == saved["tokenizer_sha256"]
    assert fingerprint(Path(args.data) / "tokenizer.json") == saved["tokenizer_sha256"]
    tokenizer = load_tokenizer(tokenizer_path)
    device = resolve_device(args.device)
    model = LucidAI(ModelConfig(**saved["config"])).to(device)
    model.load_state_dict(saved["model"])
    corpus = Corpus(Path(args.data) / "pretrain_val.bin", model.config.context_length)
    loss = evaluate(model, corpus, 1, 32, device, nullcontext)
    report = {"checkpoint": str(Path(args.checkpoint).resolve()), "step": saved["step"],
              "validation_loss_32_batches": loss, "data_metadata_sha256": fingerprint(Path(args.data) / "metadata.json"),
              "note": "Grammar scores compare mean token NLL; diagnostic preferences only, not a standardized language benchmark.",
              "grammar": [], "completions": []}
    model.eval()
    with torch.no_grad():
        for good, bad in PAIRS:
            values = []
            for sentence in (good, bad):
                ids = encode_text(tokenizer, sentence)
                _, value, _ = model(torch.tensor([ids[:-1]], device=device), torch.tensor([ids[1:]], device=device))
                values.append(value.item())
            report["grammar"].append({"grammatical": good, "ungrammatical": bad, "losses": values,
                                      "preferred_grammatical": values[0] < values[1]})
        for prompt in PROMPTS:
            ids = encode_text(tokenizer, prompt)
            result = model.generate(torch.tensor([ids], device=device), max_new_tokens=80, temperature=0,
                repetition_penalty=1.05, stop_ids=[tokenizer.token_to_id("<|eos|>")],
                banned_ids=[tokenizer.token_to_id(t) for t in SPECIAL if t != "<|eos|>"])
            completion = tokenizer.decode(result[0, len(ids):].tolist(), skip_special_tokens=True)
            report["completions"].append({"prompt": prompt, "completion": completion})
            print(prompt + completion, flush=True)
    with Path(args.out).open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f"Validation loss {loss:.4f}; grammatical preference {sum(r['preferred_grammatical'] for r in report['grammar'])}/6", flush=True)


if __name__ == "__main__":
    main()
