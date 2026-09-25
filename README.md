# Lucid AI

[Open the website](https://lucidiscool.github.io/Lucid-AI-Public/)

Lucid V5 is a local AI workspace with streaming conversations, memory controls, web research, Markdown rendering, and developer tools. The public site uses your computer for inference while you choose to run the host. It does not use a hosted AI service. Visitor chats, memories, and preferences persist in the separate private [Lucid-AI-Visitor-Data](https://github.com/Lucidiscool/Lucid-AI-Visitor-Data) repository.

## Public website: run Lucid on your PC

The GitHub Pages site serves the browser interface. Start `start-local-host.cmd` on Windows or `./start-local-host.sh` on Linux to run the model, an isolated gateway, and a temporary Cloudflare tunnel. The launcher updates the Pages backend address for that tunnel. Keep the host computer awake and the launcher open while people use Lucid; stop it when you are done. Chat and admin access are unavailable while the host is off.

The launcher prompts privately for your admin passcode. Open the website's **Admin panel** and enter the same code to review recent visitor activity. Setup details and saved-data behavior are in [ADMIN.md](ADMIN.md); private Windows and Linux installer scripts are in [Lucid-AI-Admin-Host](https://github.com/Lucidiscool/Lucid-AI-Admin-Host).

`start-public.cmd` is an equivalent Windows launcher. Both Windows and Linux launchers update and push only `website/backend.json` with the current temporary tunnel address. This requires Git and GitHub CLI authentication with push access to this code repository and the private data repository. The local public gateway isolates visitor workspaces and never exposes your personal workspace or the model server directly.

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

## Website features and laptop hosting

GitHub Pages serves the HTML, CSS, JavaScript, Markdown rendering, navigation, and browser controls.
Chat inference, Search, Research, memory storage, and admin authentication run on the host computer.
Search topics go to search providers; source pages are downloaded and analyzed on the laptop.
The public gateway allows two explicit Search/Research requests per visitor session per minute,
with topics up to 1,000 characters. Research reads at most eight sources; Search reads at most three.
Private network addresses and nonstandard web ports are blocked. Automatic web search and model
configuration remain available in the local app only.

### Automatic startup on Linux

After configuring the model and signing into GitHub CLI, run:

```bash
.venv/bin/python install-autostart-linux.py
```

This enables `lucid.target` and separate user services for the model, public host, and localhost app.
They start at boot (including before sign-in), restart after failures, and retry while networking
is unavailable. A background check looks for GitHub source updates every minute and reloads Lucid
when AI server code changes. Changes to the local model configuration or replacement model file
also trigger a reload after the file stops changing. GitHub Pages deploys website changes and open
tabs reload the new version automatically. Each public host restart creates a new Cloudflare URL
and pushes `website/backend.json`; GitHub Pages then deploys that address. The website will be
offline while the laptop is off or disconnected.

On this Fedora KDE laptop, automatic suspend is disabled on AC and battery, and closing the lid
does not suspend it. Keep it plugged in for continuous hosting: a depleted battery or loss of power
will still turn it off. The physical power button and normal shutdown controls remain available.

The installer saves the admin passcode and GitHub token in owner-only files under
`~/.config/lucid-host/credentials`; systemd supplies them to the host service at startup.
They are never written to either repository. Keep the installed project folder in place.
Rerun the installer after changing credentials or moving the project.

```bash
systemctl --user status lucid-model lucid-host lucid-local
systemctl --user status lucid-update.timer
systemctl --user restart lucid.target
systemctl --user stop lucid.target
journalctl --user -u lucid-host -n 50
```

To turn off boot hosting, run `systemctl --user disable --now lucid.target`.

### Raspberry Pi Linux host

The source is prepared for Linux ARM64, but the current laptop's `local_model.json` and Vulkan
binary are specific to this computer. Do not copy those paths or runtime files to a Pi. A Raspberry
Pi 5 with 8 GB or 16 GB RAM is the sensible starting point for this 2.5 GB quantized model; expect
slower responses than on the laptop and benchmark before sharing it publicly. Use active cooling
and a suitable 5 V / 5 A USB-C supply for sustained load. Raspberry Pi lists these RAM sizes,
VideoCore VII Vulkan support, cooling guidance, and power requirements on its [Pi 5 specifications](https://www.raspberrypi.com/products/raspberry-pi-5/).

On a 64-bit Raspberry Pi OS installation, build or install a Linux AArch64 `llama-server` on the Pi
itself, then configure `local_model.json` with the Pi's absolute paths. Start with the CPU backend
(`device` set to `none`, `gpu_layers` set to `0`) and a modest context/cache; test the Pi's Vulkan
backend separately only if its driver and `llama.cpp` build list it as a device. The upstream
[`llama.cpp` build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md) documents
Linux AArch64 CPU builds and optional Vulkan builds. The existing Linux systemd installer can then
enable the same boot services. Pi model speed and Vulkan offload are not verified by this project yet.

## Included source

- `website/`: interface, styles, and assets
- `website_server.py`: local HTTP server
- Python application, training and evaluation scripts
- `tests/`, `examples/`, and project documentation
- Verified model download manifest and setup script

Personal conversations, memories, feedback, downloaded datasets, model weights, checkpoints, installed dependencies, logs, and machine-specific configuration are excluded. Run the setup script to obtain the model/runtime rather than committing them.

The older research notes describe the original local development environment. Training scripts may require additional dependencies from `requirements.txt` or `requirements-directml.txt` and separately prepared data.

The repository retains its Apache 2.0 license. Downloaded models and runtimes retain their upstream licenses.
