# LucidAI V5 · browser edition

Start with `lucidweb` in any terminal, or double-click `start-website.cmd`. The alias `lucid5web` also works. The launcher opens http://127.0.0.1:8765 in your browser. Keep its terminal open; Ctrl+C shuts down the website. Running the launcher again reopens an existing server.

This public source distribution excludes personal data, installed dependencies, model files, runtime binaries, training data, and checkpoints. Follow README.md to install and run it. The GitHub Pages version connects to Lucid V5 on Hugging Face ZeroGPU and does not need the owner's computer. The original local server remains local-only. Free GPU queues and daily quotas apply; web research is local-only.

The browser has streaming chat, saved-conversation navigation, Markdown/code rendering and copying, latest-answer feedback, automatic memory controls, web search and research modes, visible activity, a memory manager, and developer controls. `/help` opens a searchable command library. Type slash commands into the composer as in the terminal. Search/Research buttons prefix your message with the corresponding command; explicit slash commands take precedence.

The blank canvas experiment uses the same temporary simple-English fact engine. Its messages vanish when you exit the mode; normal history returns. It does not use Qwen, external websites, or normal memories. The settings panel calls this a temporary experiment rather than erasing model weights. Process summaries show actions, not hidden reasoning.

Stopping a reply closes generation when the next token arrives. A page fetch may need to finish its timeout before cancellation takes effect. Partial stopped replies stay visible but are not saved as completed conversation turns.

The server binds only to 127.0.0.1 and validates Host, Origin and a local request token. The page uses only bundled assets; no external fonts, CDNs or frontend telemetry. Web search still contacts search providers when used. Model-generated content is rendered as text and safe HTTP(S) links; raw HTML is never executed. This is a single-user local workspace: browser tabs share the active conversation and settings. Do not expose the port to the public internet.

Inference uses V5's stateless localhost model endpoint on port 8098 if already running, avoiding another GPU allocation. If unavailable, this copy can start its own bundled runtime/model on that port. Model prompts contain only this copy's selected conversation and memory. Web port can be changed with `lucid5web --port 8766`.

Source: `website/`, `website_server.py`. Tests: `.venv-directml\Scripts\python.exe -m unittest discover -s tests -q`.
