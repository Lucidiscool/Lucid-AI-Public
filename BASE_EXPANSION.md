# Broader base-language training

## What the diagnostic established

The existing 46M-parameter base checkpoint was fitted to six short secret-word examples for 200 updates on the RX 6600. Loss fell from 12.8585 to 0.000174, and greedy generation answered all six training examples correctly. Both unseen words failed. This confirms the tested optimization path can memorize distinct examples; it does not prove general language or reasoning ability. Diagnostic weights were discarded. Full result: `runs/learning-diagnostic.json`.

The unchanged base model's raw completions show readable simple story text, but it turns unrelated explanation prompts into stories. On six small grammatical-versus-ungrammatical sentence pairs it preferred the grammatical sentence in four cases. That is an informal diagnostic, not an intelligence benchmark. The matched new-corpus validation baseline is 5.3456 over 32 deterministic batches. See `runs/base-expanded-before.json`.

## New corpus

`data/base-expanded` contains 25,323,256 training tokens and 1,838,853 validation tokens, from 64,340 training and 5,798 validation documents. The existing tokenizer is retained byte-for-byte, enabling continuation of the existing weights. All prepared-file hashes were verified, and the 15 automated tests passed, including new coverage for tokenizer reuse preserving token IDs.

Sources are bounded prefixes of [TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories) and the Khan Academy/OpenStax-derived subsets of [Cosmopedia](https://huggingface.co/datasets/HuggingFaceTB/cosmopedia). Both provide synthetic text; the corpus is not a fact-checked knowledge base. Publisher revisions, source licenses, dataset cards, download hashes, and record provenance are stored in `data/base-sources`. Prefix selection is not representative random sampling.

Complete documents are deduplicated and grouped before splitting. TinyStories publisher validation is retained; educational records use source-seed grouping. Exact/group separation does not eliminate paraphrase leakage, and the inherited tokenizer/checkpoint has prior corpus exposure. This validation should not be presented as a pristine independent benchmark.

The prepared chat files are included for compatibility with the preparation pipeline, but this run uses only the pretraining binary arrays. They do not preserve the special dialogue sampler weights; use `data/dialogue-v2-reviewed` for a future weighted dialogue experiment.

## Running experiment

`learn_base_expanded.py` initializes from `checkpoints/learning-pretrain/best.pt`, with a fresh optimizer, 10,000 updates, context 256, batch 1, accumulation 4, peak learning rate 1e-4, 200 warmup updates, seed 918, and 32 validation batches every 250 updates. This trains on 10.24 million additional sampled tokens. It is a bounded experiment, not a claim of sufficient training.

The expected duration based on prior runs is roughly 50–65 minutes. Each invocation pauses after 90 minutes at an update boundary if unfinished. Best/latest checkpoints and status are in `checkpoints/base-expanded`. Logs: `runs/base-expanded.log` and `runs/base-expanded-errors.log`. `run-directml.cmd status` displays progress.

To request a safe pause, create `PAUSE_BASE_LEARNING` in the project directory. Remove it before resuming with `.venv-directml\Scripts\python.exe learn_base_expanded.py`. Do not start duplicate trainers. A lock file prevents duplicate wrapper runs; after an abnormal process termination, verify the recorded PID is no longer running before removing a stale lock.

When complete, the wrapper writes `runs/base-expanded-after.json` with the same validation batches, grammar comparisons, and raw continuation prompts. It does not start SFT, change the chat default, or claim the checkpoint is a capable assistant. Review both language quality and validation loss before the next training decision.
