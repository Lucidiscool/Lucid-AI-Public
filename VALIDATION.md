# Verification performed

**Update:** DirectML is now installed in a separate environment and GPU training was verified on the RX 6600. See [DIRECTML.md](DIRECTML.md) for the newer GPU results. The report below records the original CPU-only verification.

Environment: existing local Python 3.12, PyTorch 2.14.0+cpu, tokenizers 0.23.2. CUDA was unavailable in this Python installation. No GPU or long-running quality training was performed.

## Correctness tests

`run.cmd test`: **7 tests passed**.

- Cached multi-token decoding agrees with full-sequence logits.
- Future tokens cannot affect earlier causal logits.
- Masked cross-entropy agrees with the selected assistant-token loss; gradient-checkpointed backward produces finite gradients.
- Greedy decoding is repeatable and oversized contexts are rejected.
- Normalized duplicate keys produce stable splits and malformed role ordering is rejected.
- User prompts are masked, assistant end tokens are supervised, batch targets shift correctly, and history is trimmed by complete turns.
- An end-to-end temporary corpus is prepared, pretrained, resumed, instruction-tuned and used for generation. Resuming from a completed CPU step reproduces uninterrupted final weights exactly. Mismatched checkpoint tokenizers are rejected.

## Real starter data

Imported the raw V3 text and conversations, plus 27 authored English/instruction examples. Trained a new 16,384-token tokenizer on the training split only.

| Prepared partition | Count |
|---|---:|
| Training paragraphs | 124,977 |
| Validation paragraphs | 6,569 |
| Pretraining train tokens | 5,561,778 |
| Pretraining validation tokens | 294,823 |
| Training conversations | 11,665 |
| Validation conversations | 608 |
| Exact duplicate paragraphs removed | 9 |
| Exact duplicate conversations removed | 2 |
| Short/low-letter-content paragraphs filtered | 23,524 |

The old text does not preserve story boundaries. Its paragraph-level validation is suitable for a starter smoke run, not a rigorous estimate of generalization. Use document JSONL with group IDs for a serious corpus. The tokenizer differs from V3, so token counts are not directly comparable.

## Actual CPU smoke runs

Trained the 2,884,736-parameter `tiny` preset with context 128 for **3 optimizer steps per stage**. These runs intentionally use separate smoke checkpoint folders.

| Stage | Initial validation loss | Final validation loss |
|---|---:|---:|
| Pretraining | 9.7416 | 9.6176 |
| Instruction tuning | 9.7458 | 9.7304 |

Instruction smoke training used 10,772 conversations and skipped 893 that exceeded the deliberately short context; validation used 566 and skipped 42. Longer production presets retain more examples.

Verified the Windows launcher, checkpoint reload, one-shot chat and evaluation report generation. Evaluation output is saved in `runs/smoke-evaluation.json`. The Windows UTF-8 console handling was corrected after a generated character exposed an encoding error.

**The smoke answers are repetitive and do not satisfy the English/reasoning review tasks.** This is expected after only six total updates from random initialization. The decreasing losses verify functioning optimization, not usable language ability. No claim is made that v4 currently outperforms the trained v3 checkpoints.

## Remaining work before judging ability

1. Assemble much more varied, high-quality English and instruction data, preserving document groups and provenance.
2. Train the base model until held-out prose is coherent; monitor overfitting.
3. Instruction-tune using correct, diverse answers and enough multi-turn examples.
4. Compare fresh held-out answers for English, reasoning, factual accuracy and instruction following.

The 46,150,144-parameter small and 122,708,736-parameter medium presets have been instantiated for size checks, but have not undergone full training. GPU mixed precision and GPU resume remain untested on this CPU-only setup. Exact reproducibility can differ across hardware or library versions.
