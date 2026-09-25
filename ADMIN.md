# Lucid Admin and visitor data

GitHub Pages serves the website and Admin interface. The computer running Lucid hosts the local model, isolated visitor gateway, and Admin API. The host publishes a temporary Cloudflare Tunnel address to `website/backend.json`; the Admin panel works while that computer is awake and connected.

## Installer

Use the private [Lucid-AI-Admin-Host repository](https://github.com/Lucidiscool/Lucid-AI-Admin-Host) while signed into GitHub. Its Windows and Linux installers clone the public project and install the Python web dependencies. They do not store the admin passcode or install a model or GPU driver.

The host computer needs Git, GitHub CLI signed into an account with push access to `Lucid-AI-Public` and read/write access to `Lucid-AI-Visitor-Data`, `cloudflared`, a configured local model, and a compatible GPU/runtime.

## Windows

1. Run `install-windows.ps1` from the private installer repository. It creates `C:\Users\<you>\Lucid-AI-Public` by default. Python 3.11+, Git, GitHub CLI, and Cloudflare Tunnel are required; the installer can install Cloudflare Tunnel with `winget`.
2. Set up your Windows model and ensure `local_model.json` points to its GGUF and `llama-server.exe`. Keep your model configuration and weights out of Git.
3. Start `start-local-host.cmd` in the public project folder. Enter the admin passcode using the hidden prompt.
4. Keep the window open while people use Lucid. Visit the website and select **Admin panel**. To stop hosting, run `stop-public.cmd` or press Ctrl+C.

## Linux

1. Run `install-linux.sh` from the private installer repository. On Debian or Ubuntu it can install Python, Git, GitHub CLI, and Cloudflare Tunnel packages when `sudo` is available. Other distributions need those tools installed first.
2. Install a Linux-compatible `llama.cpp` build for your GPU and the Lucid GGUF model. Create `local_model.json` in `~/Lucid-AI-Public`; set `server` to your Linux `llama-server`, `model` to the local GGUF, `device` to a backend available in your build (commonly `Vulkan0`), and `port`, `alias`, `context`, and `gpu_layers` to your model settings. Windows `.exe` files and Windows paths do not work on Linux.
3. Run `./start-local-host.sh` in the public project folder. Enter the admin passcode using the hidden prompt.
4. Keep the terminal open while hosting. Visit the website and select **Admin panel**. Press Ctrl+C to stop.

The model setup helper currently in the public project installs the pinned Windows Vulkan runtime. For Linux, install/build the Linux runtime and model separately; a compatible Linux build is required before starting the host.

## Saved visitor information

The private repository [Lucid-AI-Visitor-Data](https://github.com/Lucidiscool/Lucid-AI-Visitor-Data) stores visitor conversations, saved memories, settings, feedback, and research. Each browser profile is identified by a hash of a random browser key; the raw key and admin passcode are not uploaded. Local checkout defaults to `%LOCALAPPDATA%\LucidAI\VisitorData` on Windows and `~/.local/share/LucidAI/VisitorData` on Linux.

The Admin activity panel shows recent requests synced from the private data store. Full saved conversations, memories, and options remain in that private repository. Repository history retains earlier versions after data is changed or removed from the current saved view.

## Security and availability

The passcode is checked only by the host and never stored by either repository. Manual startup prompts for it privately. The optional Linux autostart installer (`.venv/bin/python install-autostart-linux.py`) stores the passcode and GitHub token in owner-only local credential files and enables systemd user services at boot. See the README for start, stop, and credential-update instructions. The gateway limits sessions and requests and does not expose the owner's workspace or model server directly. Chat, admin access, search, research, and visitor-data synchronization stop when the host computer is offline. GitHub Pages continues serving the interface.
