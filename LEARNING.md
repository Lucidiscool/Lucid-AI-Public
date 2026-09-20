# Current learning run

`learn_now.py` continues from `checkpoints/improved-pretrain/best.pt` with a fresh optimizer and learning-rate schedule. It performs 10,000 additional pretraining updates (10.24 million sampled tokens), then 2,000 SFT updates from the best new base checkpoint, then saves generated review answers. It uses the existing corpus and tokenizer; it does not download additional data. Seed 2026 provides a different batch stream from the original run.

Outputs: `checkpoints/learning-pretrain`, `checkpoints/learning-sft`, `runs/learning-review.json`. Earlier models and the chat default remain unchanged pending review. Training is not guaranteed to produce useful chat.

Progress: `run-directml.cmd status`. Logs: `runs/learning.log` and `runs/learning-errors.log`.

To pause, create an empty file named `PAUSE_LEARNING` in this project. The trainer saves after the current update, and the next stage does not start. To resume, remove that file and run `.venv-directml\Scripts\python.exe learn_now.py`. Do not start a second copy while training is active.

Each invocation has a 90-minute limit for pretraining and a 30-minute limit for SFT, pausing safely if reached. Keep the computer awake for training. No automatic replacement of the current chat model is performed.
