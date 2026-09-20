# LucidAI V5 developer edition

Start with `lucid5` in a terminal, or double-click `chat-dev.cmd`. The startup banner points to `/help`, which lists every command. `lucid` continues to start V4.

V5 is a separate copy of V4 including the pretrained model, runtime, original checkpoints, training data, Python dependencies and existing personal data as of the copy. Later changes do not sync. Normal V5 chat uses its own `personal/` folder and model server on port 8098. The copied model is the same Qwen backbone, not a newly trained model. Running V4 and V5 servers simultaneously uses additional GPU memory.

`/think` toggles clear process summaries: whether a local planner is being used, which query is searched, the number of context turns and memories, generation settings, elapsed time and persistence. These are app-level explanations, not raw hidden reasoning or a dump of model internals. Tool activity and saved-memory notices stay visible even with this toggle off.

`/forget` or `/forget on` enters an isolated, temporary fact experiment. Normal chat pauses. This mode uses a small deterministic English parser, not Qwen: it has no factual knowledge, web access, normal memories or automatic saving. For example:

```text
/forget on
Are you a human?
Yes you are a human
Are you a human?
/facts
/forget off
```

The first question gets “I don't know”; after teaching it, the second acknowledges the taught fictional fact. It does not actually become human. English support is limited to simple `X is Y`, `you are Y`, `I am Y`, and `is/are/what/who` questions; it is not a general language model with its knowledge erased. Unrecognized requests return “I don't know”. `/teach STATEMENT` also teaches; `/reset` clears experimental facts. Leaving the mode, quitting, or restarting discards all those facts. The previous normal conversation resumes. `/forget ID` and `/forget all` still remove normal saved memories outside the experiment.

Developer controls: `/temperature 0..2`, `/tokens 32..4096`, `/system TEXT`, `/system reset`, `/settings`, `/model`, `/stats`, `/history`. These generation and prompt settings are session-only; automatic web/memory switches persist. `/search` and `/research`, feedback commands, saved chats and automatic memory retain V4 behavior in normal mode.

Run tests with `.venv-directml\Scripts\python.exe -m unittest discover -s tests -q`.
