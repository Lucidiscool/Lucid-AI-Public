# LucidAI v4 improvement run

## Implementation

- Fixed safe pause: Ctrl+C, stop files, and session time limits now stop at a completed optimizer update and save `latest.pt`.
- Added atomic `status.json` reporting and `run-directml.cmd status`.
- Checkpoints retain trained-token counts, elapsed time, and last validation loss across resumes.
- Restored the original interrupt handler when training exits; non-finite validation loss fails explicitly.
- Fixed data preparation to honor explicit source partitions and group IDs. Connected duplicate records and shared opening prompts cannot straddle partitions; validation takes priority.
- Generation computes only the last token's vocabulary projection while preserving the full KV cache. Invalid sampling settings fail with clear errors.
- Fixed one-shot chat prompts beginning with slash commands so they cannot enter an interactive command loop.
- Added `chat-directml.cmd` to open GPU chat with the default SFT checkpoint.

## Verification

13 automated tests pass in the existing DirectML Python environment. Coverage includes exact CPU resume, stop-file pause and resume, token counters, complete preparation/training/chat, group and official partition preservation, cache equivalence, causality, loss masking, and optimizer restoration. A separate test on the RX 6600 confirms final-token vocabulary projection matches full logits and generates tokens successfully.

## Training

The 46,150,144-parameter small model was trained from scratch on the existing prepared corpus at context 256, batch size 1, accumulation 4, FP32 on the RX 6600. Pretraining completed 1,000 updates (1,024,000 tokens), reducing validation loss from **9.8081 to 3.3195**. Best and latest weights are in `checkpoints/improved-pretrain`.

Instruction tuning completed 500 updates on 11,662 conversations that fit the context, supervising 55,684 answer tokens. The learning rate peaked at 1e-4 with 50 warmup updates. Validation used 24 deterministic batches and improved from **10.2395 to 3.8650**. Best and latest weights are in `checkpoints/sft`, which is the default chat location. Three training conversations and one validation conversation were skipped because they exceeded context.

Pretraining took about 310 seconds; instruction tuning took about 152 seconds. Both runs are complete, and no training process was left running.

## Answer quality review

The baseline checkpoint returned repeated punctuation. The new checkpoint produces short sentences and ends its turns, but its responses are repetitive and unrelated to the prompts. On my inspection, **none of the eight review cases passes its rubric**, including grammar correction, reading comprehension, arithmetic, instruction following, and conversation memory. This is an assistant review, not a human score or standardized benchmark. The raw output files keep their human-score fields unset.

Compare `runs/before-improvements.json` with `runs/after-improvements.json`. The run improved language-model loss and output structure, but did **not** produce a useful general assistant. These failed review prompts were not added to training.

## Limits

The existing prepared corpus is preserved for tokenizer compatibility. Its paragraph-level pretraining split has known related-story leakage risks, and it was prepared before the stronger partition rules. The validation figures measure this corpus, not a rigorous general intelligence benchmark. Loss changes across pretraining and instruction tuning are not directly comparable because the datasets and loss masks differ.

This is still a small experimental model. A short training session cannot establish broad reasoning or factual reliability. Expanding and auditing the corpus, preparing fresh data with the corrected splitter, and substantially more training remain necessary for a capable general assistant. Original V3 files and earlier checkpoints were not changed.

## Use

Double-click `chat-directml.cmd`, or run:

```powershell
.\run-directml.cmd chat --device directml
.\run-directml.cmd status
.\run-directml.cmd test
```

The original training metrics are in each checkpoint directory's `metrics.jsonl`; `status.json` records completion or pause. The default trained model has a 256-token context, shorter than the small architecture's 1,024-token default; older turns will be trimmed to fit.
