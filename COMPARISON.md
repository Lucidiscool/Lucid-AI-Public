# V3 and V4 comparison

## What the answers show

Compared `lucidai_v3_best.pt`, `lucidai_v31_best.pt`, and V4 `learning-sft/best.pt` on the same 17 prompts. All used CPU greedy decoding, 64 new tokens, structural tokens suppressed, and no repetition penalty. Each model used its own tokenizer and native conversation delimiters. This isolates checkpoint behavior from V4's usual repetition penalty. It does not make losses across different tokenizers comparable.

| Prompt | V3 | V3.1 | V4 after long run |
|---|---|---|---|
| Hello! | Hey there. Ask me anything you'd like help with. | Hey! What would you like help with? | A good idea. |
| What is 2 + 3? | 10 | 1 | 1 |
| What is 17 + 26? | 144 | 16 | 1 |
| What color is Lena's red cup? (full prompt in JSON) | No. | Repeated unrelated adjectives | Repeated warm-sun phrase |

V3's greeting is clearly better. Neither V3 checkpoint reliably solves the basic questions. All three fail the seven single-turn writing, reasoning, reading, and instruction review cases on inspection. The general questions are not a standardized benchmark, and some familiar prompts already occur in the older training corpus.

Full unedited outputs: `runs/compare-v3.json`, `runs/compare-v31.json`, `runs/compare-v4.json`.

## Evidence about the cause

- The source conversations contain 12,275 records before deduplication, but only 13 multi-turn records. The Dolly-derived question-answer data accounts for 91.85% of the 330,664 assistant target tokens. This is not a balanced conversational dataset.
- V3.1's preparation metadata shows 12 distinct training conversation examples expanded to 1,200 samples. Repeated exposure to familiar chat phrases plausibly explains its better greetings; this does not establish general conversational ability.
- V3 saved best checkpoints report 4,000 pretraining updates and 4,000 chat updates; V3.1 reports 400 balancing updates. They do not save enough run settings to reconstruct exact token exposure reliably. V4 is also much larger (46.15M parameters versus approximately 8.9M for V3; exact counts are in the comparison JSON).
- V4's current lineage saw 11.264 million pretraining tokens, then 218,179 SFT answer tokens. The earlier 500-step SFT checkpoint is a separate branch, not part of this lineage. Step totals alone are misleading when batches and sequence lengths differ.
- In a diagnostic on 48 held-out single-turn examples, V4 gave the correct answer a lower teacher-forced loss with the correct question than with a mismatched question in 45 cases. Mean losses were 5.359 versus 6.237, with equal weight per example. It does use the question; this is not evidence of a completely disconnected prompt path. It is not a generation accuracy score.

Raw evidence: `runs/training-audit.json` and `runs/conditioning-probe.json`. Existing V4 validation data retains the previously documented split limitations.

## Next experiment

A separate concise-chat curriculum reuses 507 training and 27 validation conversations from the existing chat and English sources. It excludes numeric legacy chat examples and exact comparison prompts, preserves the existing split assignments and tokenizer, and starts from `learning-sft/best.pt`. These are existing examples, not newly acquired data. The validation subset has been used in earlier V4 runs, so this is a diagnostic regression test, not an untouched final test set.

The bounded experiment uses 500 optimizer updates, accumulation 4, peak learning rate 1e-4, and deterministic validation every 100 updates. Output: `checkpoints/chat-curriculum`. The default chat checkpoint is not changed automatically.

This tests whether more concentrated exposure to concise conversation improves responses. It does not solve the lack of diverse multi-turn data, factual coverage, or general instruction-following.

## Experiment result

All 500 updates completed. Curriculum validation loss declined from 3.7724 to 2.3850. The candidate now answers `Hello!` with `Hello! What are you working on today?`, and the clear-sky question with `The sky is blue.` Both answers were poor before the experiment. The exact comparison prompts were excluded from this curriculum, but related training phrases remain; this is limited transfer, not proof of broad generalization.

Most of the other 15 comparison answers are still incorrect, and all seven harder review cases still fail. Many responses now drift into programming definitions, reflecting the narrow legacy chat source. The candidate is therefore **not promoted to the default chat model**. Raw outputs: `runs/compare-v4-curriculum.json`. To inspect it manually, use `chat-candidate.cmd`.

The 13 existing automated tests passed. Additional checks verified curriculum file hashes, exact train/validation separation, and target-label alignment. Neither V3 nor existing model checkpoints were changed. No training job remains active from this experiment.

## Decision

Keep V3 available for familiar small talk. Do not merge its incompatible weights into V4 or treat its good greeting as evidence of stronger general reasoning. Keep the new V4 candidate as a diagnostic checkpoint.

The next substantive improvement should be a reviewed dialogue dataset balanced across greetings, clarification, everyday factual explanations, writing, and multi-turn context. Split related conversations by topic/template before tokenization, reserve fresh evaluation prompts, inspect answer-token shares as well as record counts, and retain a small general-instruction replay set so conversational tuning does not push every answer toward one domain. Avoid generating thousands of near-identical arithmetic examples or simply repeating a handful of greetings. Broader language training is still needed; this comparison does not establish an adequate training budget.
