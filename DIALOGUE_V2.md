# Dialogue data and controlled training trial

## Dataset

The prepared SFT dataset is `data/dialogue-v2-reviewed`. It retains the existing V4 tokenizer and fits the checkpoint's 256-token context without truncating replies.

- Training: 1,708 conversations, including 243 with multiple user/assistant exchanges.
- Validation: 93 conversations, including 11 with multiple exchanges.
- Training sources: 1,160 OpenAssistant paths, 48 newly assistant-authored dialogues, 27 existing English examples, and 473 existing instruction examples for replay.
- New authored dialogues cover clarification, writing edits, everyday explanations, reference tracking, changing preferences, and ordinary conversation. They are synthetic examples, not independent human data.

OpenAssistant source: [publisher dataset card](https://huggingface.co/datasets/OpenAssistant/oasst1), revision `fdf72ae0827c1cda404aff25b6603abec9e3399b`, Apache-2.0. The downloaded card, license, source files, SHA-256 hashes, and provenance manifest are retained under `data/dialogue-sources`. Original instruction replay retains its existing source provenance and license requirements; this mixed dataset is not wholly Apache-2.0.

Collection uses the source's English, review, quality, and rank annotations. A 25-example source sample was inspected, and 15 problematic source IDs were recorded with reasons in `examples/dialogue_exclusions.json`; all associated conversation trees were excluded. This is a spot-check, not a factual audit of every selected answer. A separate first-pass dataset at `data/dialogue-v2` is retained as an audit artifact and is not used for the trial.

## Balance and separation

Sampling weights target expected sampled assistant-token shares of 45% dialogue, 20% explanation, 15% writing, 15% general replay, and 5% technical content. These are sampling targets, not guaranteed optimizer-gradient shares. Categories are heuristic. There is no mass duplication of the greeting examples.

`data.py` supports optional positive finite sampling weights. Existing unweighted datasets keep their original sampling path, preserving reproducible resume behavior. Validation remains unweighted.

The builder preserves official OpenAssistant partitions and existing legacy validation constraints. Related conversation trees and matching user prompts remain together. One complete selected path is kept per OpenAssistant tree. Validation takes priority when connections conflict. Overlong conversations are rejected rather than cut off.

Twelve newly reserved review cases are in `examples/dialogue_holdout.json`. Their exact prompts and the earlier comparison prompts are excluded from this dataset. The context tests supply fixed assistant history so both checkpoints receive identical inputs; they do not test a fully generated conversation. After this experiment these are regression cases, not a permanently untouched benchmark.

## Verification

All 15 automated tests passed, including weighted sampling frequency, invalid-weight rejection, RNG restoration, original exact-resume behavior, loss masks, and cached generation. `verify_dialogue_data.py` also checked artifact hashes, encoded label alignment, context lengths, train/validation group and prompt separation, legacy validation exclusion, reserved-prompt exclusion, and expected token shares. Its result is saved in `runs/dialogue-data-verification.json`.

## Trial configuration

The trial initializes from `checkpoints/chat-curriculum/best.pt` with a fresh optimizer, using 500 updates, batch size 1, accumulation 4, peak learning rate 5e-5, 50 warmup updates, seed 917, and validation every 100 updates using 48 deterministic batches. It runs on the RX 6600 and saves separately to `checkpoints/dialogue-v2-trial`.

Baseline review: `runs/dialogue-v2-before.json`. Training statistics: `checkpoints/dialogue-v2-trial/metrics.jsonl` and `status.json`. The default chat model is not automatically replaced.

## Completed result and decision

All 500 updates completed. Initial validation loss was 5.9685; the best validation loss was 4.7526 at step 300, and final loss was 4.7579. Answer review therefore used the step-300 `best.pt`, not simply the final checkpoint.

The reserved twelve-case review did not establish useful conversation: on assistant inspection, none of the new checkpoint's answers passed the supplied rubric. It failed to recall orange, ignored the corrected meeting day, did not ask for missing information, and produced unrelated text instead of a rewrite or explanation. CPU and DirectML reviews were both run; the matched-CPU before/after artifacts are `runs/dialogue-v2-before.json` and `runs/dialogue-v2-after-cpu.json`. The GPU artifact is `runs/dialogue-v2-after.json`.

The older 17-prompt comparison is saved in `runs/compare-v4-dialogue-v2.json`. The greeting remains appropriate, but the candidate's earlier correct clear-sky answer regressed into unrelated story text. This does not justify replacing either the default chat model or `chat-candidate.cmd`'s checkpoint. Both launchers remain unchanged.

The actual planned sampling stream contained about 44.1% dialogue answer tokens and 5.7% technical answer tokens, close to the target mix. See `runs/dialogue-v2-sampled-mixture.json`. The failure cannot be attributed simply to the sampler ignoring the new weights.

No training job remains running from this trial. The dataset and tools are available for future experiments, but this result argues against another blind instruction-tuning extension. A further from-scratch effort needs a stronger, broader base-language model and explicit capability gates before chat tuning. This trial does not prove that any particular larger training budget will solve the problem.
