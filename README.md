# Lucid AI

[Open the website](https://lucidiscool.github.io/Lucid-AI-Public/)

Lucid V5 is a local AI workspace with streaming conversations, memory controls, web research, Markdown rendering, and developer tools. The public site uses your PC for inference while you choose to run the PC host. It does not use a hosted AI service. Visitor chats, memories, and preferences persist in the separate private [Lucid-AI-Visitor-Data](https://github.com/Lucidiscool/Lucid-AI-Visitor-Data) repository.

## Public website: run Lucid on your PC

The GitHub Pages site serves the browser interface. Start `start-local-host.cmd` on your computer to run the model, an isolated gateway, and a temporary Cloudflare tunnel. The launcher updates the Pages backend address for that tunnel. Keep your PC awake and the launcher open while people use Lucid; stop it when you are done. Chat and admin access are unavailable while your PC host is off.

The launcher prompts privately for your admin passcode. Enter `3553`. Open the website's **Admin panel** and enter the same code to review recent visitor activity. Setup details and saved-data behavior are in [ADMIN.md](ADMIN.md).

`start-public.cmd` is an equivalent launcher. Both update and push only `website/backend.json` with the current temporary tunnel address. This requires Git, RTK, GitHub CLI authentication with push access to this code repository and the private data repository, and an available Git remote. The local public gateway isolates visitor workspaces and never exposes your personal workspace or the model server directly.

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

The model setup downloads the pinned Qwen GGUF (about 2.5 GB) and Windows Vulkan llama.cpp runtime using the checksums in `runs/local-model-sources.json`. It creates a machine-specific `local_model.json`. A compatible Vulkan GPU and sufficient memory are required for the default configuration. Once installed, model inference runs locally.

Open http://127.0.0.1:8765 and keep the server terminal running. This local app is designed for a single user on localhost.

## Included source

- `website/`: interface, styles, and assets
- `website_server.py`: local HTTP server
- Python application, training and evaluation scripts
- `tests/`, `examples/`, and project documentation
- Verified model download manifest and setup script

Personal conversations, memories, feedback, downloaded datasets, model weights, checkpoints, installed dependencies, logs, and machine-specific configuration are excluded. Run the setup script to obtain the model/runtime rather than committing them.

The older research notes describe the original local development environment. Training scripts may require additional dependencies from `requirements.txt` or `requirements-directml.txt` and separately prepared data.

The repository retains its Apache 2.0 license. Downloaded models and runtimes retain their upstream licenses.
