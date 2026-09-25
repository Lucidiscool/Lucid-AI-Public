# Lucid admin and visitor data

Lucid AI runs on your PC. GitHub Pages serves the browser interface, and a temporary Cloudflare tunnel lets it reach the local model gateway while your PC host is running. The Admin panel is linked in the website sidebar. It can sign in only while the PC host and its tunnel are online.

## Start the PC host

1. Start `start-local-host.cmd` in this folder. It asks for the admin passcode using hidden input; enter `3553`.
2. The launcher starts the existing local model, clones or updates the private visitor-data repository under `%LOCALAPPDATA%\LucidAI\VisitorData`, and starts the isolated gateway and Cloudflare tunnel.
3. The launcher publishes the current tunnel URL to `website/backend.json` in this repository. GitHub Pages deploys the new address automatically.
4. Open the website, select **Admin panel**, and sign in with `3553`. Keep the PC awake and the launcher open. Stop sharing with Ctrl+C or `stop-public.cmd`.

If Admin says to start the PC host, the page itself loaded successfully but has no active PC connection. Start the launcher and reload Admin after the website finishes updating. The passcode is checked by the PC gateway and is not saved in either repository.

## Saved visitor information

The private repository [Lucid-AI-Visitor-Data](https://github.com/Lucidiscool/Lucid-AI-Visitor-Data) stores each browser profile's conversations, saved memories, automation options, generation settings, feedback, and research files. Files are grouped by a hash of a random browser key; the raw key and admin passcode are not uploaded. The repository must stay private.

Visitors are told on the site that messages, memories, and preferences are saved and that the owner can review them. Data is kept in the private repository and its Git history. Clearing a memory in Lucid removes it from the current saved view, but old repository commits retain earlier versions. The Admin panel's activity list shows recent requests; conversation files remain available in the private data repository.

The PC keeps a local checkout at `%LOCALAPPDATA%\LucidAI\VisitorData` and syncs completed requests to GitHub. The host requires `gh` authentication with access to both repositories, Git, RTK, the local model and `local_model.json`, the `.venv-directml` Python environment (or the sibling `lucid ai v5 web` environment), and `runtime/cloudflared.exe`. It does not download model weights when starting.

The gateway isolates visitor workspaces, limits sessions and requests, and does not expose your personal workspace or model server. Visitor requests pass through Cloudflare's temporary tunnel and your PC. A tunnel outage does not move inference to another service.
