# Lucid admin setup

The website stays on GitHub Pages. Its Admin panel uses the existing Hugging Face Space as the control service. Password checks, activity, and hosting selection run on the backend; there is no password in website code or GitHub configuration.

## Deploy

1. Deploy the website changes through the existing Pages workflow.
2. Update the Hugging Face Space using `hosting/huggingface/DEPLOY.md`, including **admin_service.py** from the repository root.
3. In the Space Settings → Variables and secrets, add a **Secret** named `LUCID_ADMIN_PASSCODE`. A 4–512 character passcode is supported. Do not use a public Variable, commit it, or put it in backend.json. Restart the Space after changing the secret.
4. Open the website's Admin panel and sign in. Login sessions last 30 minutes and are kept only in browser memory. Passcodes shorter than 12 characters allow five login attempts per hour across the server; longer passcodes allow five per minute. Without a configured secret, admin access is disabled.

Hugging Face secret documentation: https://huggingface.co/docs/hub/spaces-overview#managing-secrets-and-environment-variables

## Switch to the PC

Click **Enable local hosting** and copy `.\start-local-host.cmd` into PowerShell opened in this repository. The launcher uses the existing Python environment and asks for the same admin passcode with hidden input. It starts the local model, bounded public gateway, and Cloudflare tunnel. Paste the HTTPS tunnel address into the panel. The cloud service checks the host before switching new visitor connections.

Prerequisites: the existing local model and `local_model.json`, `.venv-directml` Python environment (or the sibling `lucid ai v5 web` environment), and `runtime/cloudflared.exe`. See README.md for model setup. The launcher does not install dependencies or download a model. Other installations may run `python host_public.py --admin` using their configured Python interpreter.

Keep the terminal open and the PC awake. To return to cloud inference, click **Use cloud hosting**, then stop the PC launcher with Ctrl+C. The switch does not migrate chats or stop processes. Existing visitors stay on their current session until reload. It does not overwrite backend.json or push to GitHub. The older `start-public.cmd --publish` workflow is not used.

## Activity and limits

The site and direct cloud app disclose owner review of messages, replies, and feature usage. Only new requests after this update are recorded. No access to older browser sessions, the owner's personal chat files, or visitor identity is added. Admin content is rendered as text, not executable HTML.

Each host keeps at most 2,000 request records in RAM for up to 24 hours, removed on subsequent record/read operations; all disappear on restart. The panel shows the latest 200 and counts across all retained records. These are session counts, not unique people. Chat content is truncated to 4,000 input and 8,000 reply characters. Commands count as features. No persistent analytics database is included.

Select cloud or PC activity in the panel. PC review uses its own server authentication; set the same passcode through the launcher and sign in again after switching hosts. Activity never gets copied between hosts.

The cloud control service must remain available even during PC inference. Hosting selection is in cloud process memory and **resets to cloud after a restart or sleep that restarts the process**. A PC outage does not silently move an active conversation elsewhere. Free GPU quotas and queues still apply to cloud inference.

## Verification

Run `python -m unittest discover -s tests -p test_admin.py -v`, `test_cloud_session.py`, and `test_public_server.py` with the existing Python environment. Run `node --check website/admin.js` and `node --check website/app.js`.
