# Lucid AI

[Open the website](https://lucidiscool.github.io/Lucid-AI-Public/)

Lucid V5 is a local AI workspace with streaming conversations, memory controls, web research, Markdown rendering, and developer tools. The website preserves the original Lucid interface.

## GitHub Pages

The public website chats with **Lucid V5 hosted on free Hugging Face ZeroGPU**, independently of the owner's computer. GitHub Pages hosts the interface and the [Lucid V5 Space](https://huggingface.co/spaces/lucidpy/lucid-ai-v5) runs the AI. No paid AI API is used. Free GPU queues, daily visitor quotas, and Space sleep/restarts apply; this is not guaranteed uninterrupted hosting.

The hosted adapter reuses V5's DeveloperChat, memory, feedback, and experiment code. It runs the same underlying Qwen3-4B-Instruct-2507 model in Transformers BF16 instead of Windows llama.cpp Q4 GGUF; precision and sampling can change individual responses. Each page connection has a separate temporary Gradio session with in-memory chats and memories. Messages go to Hugging Face, not the owner's computer. Refreshes, expiration, restarts, or sleep can lose session data. There is a 512-token reply ceiling and 100-request session limit. Web research and model/system configuration remain local-only. The owner's personal data is not uploaded.

Changes pushed to `main` automatically deploy the `website/` folder through `.github/workflows/pages.yml`. Only website assets are deployed to Pages.

## Cloud hosting

Your computer can be off. No local launcher is needed for website chat. Source and update instructions are in `hosting/huggingface/DEPLOY.md`. The website uses the official Gradio JavaScript client 2.7.0 through jsDelivr and connects to `lucidpy/lucid-ai-v5`.

## Previous PC-hosted option

After local model setup, put the official Windows `cloudflared.exe` in `runtime/`. This installation uses Cloudflare release `2026.9.1`, SHA-256 `2837888cc0f5d58f15b6dc478376de90b4d3ba5241c7947455d1e0a0df429712`. Install Git, RTK, and authenticate GitHub CLI for repository pushes.

- `start-public.cmd` was used for the old PC/tunnel deployment. It now refuses to overwrite a configured Hugging Face connection. To intentionally restore PC hosting, first replace the cloud configuration in `website/backend.json` with a tunnel configuration.
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
