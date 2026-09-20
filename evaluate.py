"""Generate repeatable, held-out answers for human review. Not an intelligence score."""
import argparse
import json
import sys
from pathlib import Path
import torch
from chat import ChatSession

CASES = [
    ("grammar", "Correct the grammar without changing the meaning: She don't like apples, but yesterday she eat two.",
     "Correct subject-verb agreement and past tense; retain the original meaning."),
    ("writing", "Write a polite two-sentence email asking to move our Friday meeting to Monday.",
     "Exactly two sentences, polite request, correct days, natural English."),
    ("reading", "Maya put the blue notebook in a drawer and the red notebook on a shelf. Where is the blue notebook?",
     "In a drawer; no invented details."),
    ("reasoning", "A box holds 12 pencils. I give away 5 and buy 8 more. How many pencils do I have now?",
     "15 pencils with consistent arithmetic."),
    ("instructions", "Give exactly three tips for keeping a desk tidy. Use a numbered list.",
     "Exactly three useful tips in a numbered list."),
    ("explanation", "Explain why ice melts in a warm room in simple English.",
     "Accurate explanation of heat transfer and melting, understandable English."),
    ("uncertainty", "What is the name of my neighbor's dog?",
     "Acknowledges that the name is unknown instead of inventing one."),
]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="checkpoints/sft/best.pt")
    parser.add_argument("--out", default="runs/evaluation.json")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda", "directml"], default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=120)
    args = parser.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(1337)
    session = ChatSession(args.checkpoint, args.device)
    results = []
    for category, prompt, rubric in CASES:
        session.history.clear()
        answer, ended = session.answer(prompt, max_new_tokens=args.max_new_tokens, temperature=0)
        results.append(dict(category=category, prompt=prompt, answer=answer, rubric=rubric,
                            ended_naturally=ended, human_score=None))
        print(f"\n[{category}] {prompt}\n{answer}", flush=True)
    session.history.clear()
    first, _ = session.answer("My favorite color is green.", max_new_tokens=args.max_new_tokens, temperature=0)
    answer, ended = session.answer("What is my favorite color?", max_new_tokens=args.max_new_tokens, temperature=0)
    results.append(dict(category="conversation", prompt="My favorite color is green. / What is my favorite color?",
        first_answer=first, answer=answer, rubric="Remembers green from the preceding user turn.",
        ended_naturally=ended, human_score=None))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump({"checkpoint": str(Path(args.checkpoint).resolve()), "stage": session.stage,
                   "step": session.step, "scoring": "Human review: 0=fail, 1=partial, 2=pass. Do not train on these prompts.",
                   "results": results}, stream, ensure_ascii=False, indent=2)
    print(f"\nReview answers and rubric in {output.resolve()}")


if __name__ == "__main__":
    main()
