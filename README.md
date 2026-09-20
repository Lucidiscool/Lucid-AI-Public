# Lucid AI

[Open the website](https://lucidiscool.github.io/Lucid-AI-Public/)

Lucid V5 is a local AI workspace with streaming conversations, memory controls, web research, Markdown rendering, and developer tools. The website preserves the original Lucid interface.

## GitHub Pages

The public website chats with the owner's **existing Lucid V5 Python app and Qwen3-4B model**, running on the owner's computer. GitHub Pages hosts the interface; a free Cloudflare Quick Tunnel connects it to `public_server.py`. No paid AI API is used. The computer, model, gateway, and tunnel must remain running. This is a small public demo, not an always-on hosted service; Quick Tunnels have no uptime guarantee and change address on restart.

Each visitor receives a random session token and a separate temporary workspace. Messages and replies pass through Cloudflare and are stored temporarily on the host computer. Visitors cannot access the owner's personal conversations or each other's sessions. Sessions expire after one hour without requests and are cleaned up when another session is created, or when the gateway exits normally. The public gateway accepts at most 12 sessions, one active AI request, 10 messages/commands per minute per session, and 100 requests per session. Web research and model/system configuration are available only in the local app. Memory, feedback, conversation controls, and the blank experiment remain isolated to each visitor session.

Changes pushed to `main` automatically deploy the `website/` folder through `.github/workflows/pages.yml`. Only website assets are deployed to Pages.

## Start or stop public chat (host computer)

After local model setup, put the official Windows `cloudflared.exe` in `runtime/`. This installation uses Cloudflare release `2026.9.1`, SHA-256 `2837888cc0f5d58f15b6dc478376de90b4d3ba5241c7947455d1e0a0df429712`. Install Git, RTK, and authenticate GitHub CLI for repository pushes.

- Run `start-public.cmd` to start the model, gateway, and a free tunnel. It updates `website/backend.json` and pushes the new address to GitHub Pages. Allow the deployment to finish, then reload the website.
- Run `stop-public.cmd` to stop the gateway and tunnel. The local model remains available to your local app.
- Logs are in `runs/public-host.log`, `runs/public-gateway.log`, and `runs/public-tunnel.log`. Do not commit logs or `local_model.json`.

Keep the host computer awake while sharing. No Windows startup task is installed. Electricity and internet usage still apply. Never tunnel the original `website_server.py` or the model's port directly; the public gateway exposes only isolated, limited sessions.

## Run the full app locally (Windows)

Install Python 3.11 and Git, then run:

```powershell
git clone https://github.com/Lucidiscool/Lucid-AI-Public.git
cd Lucid-AI-Public
py -3.11 -m venv .venv-directml
.\.venv-directml\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv-directml\Scripts\python.exe setup_open_model.py
.\start-website.cmd
```

The model setup downloads the pinned Qwen GGUF (about 2.5 GB) and Windows Vulkan llama.cpp runtime using the checksums in `runs/local-model-sources.json`. It creates a machine-specific `local_model.json`. A compatible Vulkan GPU and sufficient memory are required for the default configuration.

Open http://127.0.0.1:8765 and keep the server terminal running. The backend is designed for a single user on localhost. A public AI service requires separate backend hosting, authentication, user isolation, and resource limits; do not expose this local server directly.

## Included source

- `website/`: interface, styles, and assets
- `website_server.py`: local HTTP server
- Python application, training and evaluation scripts
- `tests/`, `examples/`, and project documentation
- Verified model download manifest and setup script

Personal conversations, memories, feedback, downloaded datasets, model weights, checkpoints, installed dependencies, logs, and machine-specific configuration are excluded. Run the setup script to obtain the model/runtime rather than committing them.

The older research notes describe the original local development environment. Training scripts may require additional dependencies from `requirements.txt` or `requirements-directml.txt` and separately prepared data.

The repository retains its Apache 2.0 license. Downloaded models and runtimes retain their upstream licenses.
