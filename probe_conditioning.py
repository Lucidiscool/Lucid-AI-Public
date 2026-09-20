"""Measure answer loss with correct vs mismatched questions on held-out rows."""
import json
from pathlib import Path
import random
import sqlite3
import torch
from chat import ChatSession
from tokenizer import encode_messages

ROOT = Path(__file__).resolve().parent


def main():
    torch.set_num_threads(4)
    session = ChatSession(ROOT / "checkpoints/learning-sft/best.pt", "cpu")
    with sqlite3.connect(ROOT / "data/prepared/records.sqlite") as db:
        rows = [json.loads(body) for (body,) in db.execute("SELECT body FROM records WHERE kind='chat' AND split='val' ORDER BY key")]
    rows = [r for r in rows if len(r) == 2 and len(encode_messages(session.tokenizer, r)[0]) < 160]
    random.Random(42).shuffle(rows)
    rows = rows[:48]
    results = []
    with torch.no_grad():
        for index, messages in enumerate(rows):
            losses = []
            for question in (messages[0], rows[(index + 1) % len(rows)][0]):
                ids, labels = encode_messages(session.tokenizer, [question, messages[1]])
                _, loss, _ = session.model(torch.tensor([ids[:-1]]), torch.tensor([labels[1:]]))
                losses.append(loss.item())
            results.append({"question": messages[0]["content"], "correct_loss": losses[0], "mismatched_loss": losses[1]})
    summary = {"samples": len(rows), "correct_question_mean_loss": sum(r["correct_loss"] for r in results)/len(rows),
               "mismatched_question_mean_loss": sum(r["mismatched_loss"] for r in results)/len(rows),
               "correct_question_better_count": sum(r["correct_loss"] < r["mismatched_loss"] for r in results),
               "note": "Equal weight per answer; teacher-forced loss, not a generation score.", "results": results}
    (ROOT / "runs/conditioning-probe.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
