# Lucid admin setup

Lucid AI runs on your PC. The GitHub Pages site contains only the browser interface; it sends chat requests to the temporary HTTPS tunnel started by your PC. When the PC host is stopped or asleep, chat and the Admin panel are unavailable. No hosted model service is used.

## Start the PC host

1. Deploy the website assets through the existing GitHub Pages workflow.
2. Start `start-local-host.cmd` (or `start-public.cmd`) in this folder. The launcher asks for the admin passcode using hidden input. Enter `3553`.
3. The launcher starts the existing local model, the isolated public gateway, and a temporary Cloudflare tunnel. It updates `website/backend.json` with the tunnel address and pushes that one config file to the `main` branch so the Pages site can reach this running PC.
4. Keep the terminal open and the computer awake. Open the site and select **Admin panel**. Sign in with `3553`. Stop sharing with Ctrl+C or `stop-public.cmd`.

The launcher needs Git, RTK, GitHub CLI authentication with push access, the existing model and `local_model.json`, the `.venv-directml` Python environment (or the sibling `lucid ai v5 web` environment), and `runtime/cloudflared.exe`. It does not install dependencies or download the model. Alternatively, run `python host_public.py --admin --publish` with your configured Python interpreter.

The passcode is checked only by the local gateway. It is not embedded in website assets or saved in the repository. Admin sessions last 30 minutes; five failed attempts are allowed per hour for this four-digit passcode.

## Activity and limits

The admin panel can review new visitor messages, replies, and feature usage while the PC host is running. Each gateway keeps at most 2,000 request records in RAM for 24 hours; all records disappear when it stops. The panel shows the latest 200. Counts represent sessions, not identified people. Messages are truncated to 4,000 input and 8,000 reply characters. Activity is not written to disk.

The public gateway keeps visitors isolated, limits sessions and requests, and exposes only chat endpoints. It does not expose your personal workspace or model server. Visitors' requests pass through Cloudflare's temporary tunnel and your PC. Do not share sensitive information. A tunnel outage does not move inference to another service.
