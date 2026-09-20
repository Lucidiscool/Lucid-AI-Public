# Update the hosted Lucid V5 app

Space: https://huggingface.co/spaces/lucidpy/lucid-ai-v5

Use the Space's Files → Contribute → Upload files screen. Upload these files to its root:

- `app.py`, `requirements.txt`, and `README.md` from this folder
- `dev_chat.py`, `local_chat.py`, `chat_store.py`, `chat_automation.py`, `blank_experiment.py`, and `LICENSE` from the repository root

Keep ZeroGPU Free selected. Do not upload personal files or Windows model/runtime binaries. The app loads a pinned copy of Qwen3-4B-Instruct-2507 from the model publisher at startup and uses the original V5 app logic with a cloud backend adapter.

After a deployment, wait for Running status and test a reply before changing the website connection. Website cloud configuration:

```json
{"provider":"huggingface","space":"lucidpy/lucid-ai-v5"}
```

This belongs in `website/backend.json`. The website uses the official Gradio JavaScript client 2.7.0 through jsDelivr. Each page connection receives its own temporary Gradio session. It does not use the local PC tunnel when the provider is `huggingface`.

Free GPU requests have queues and daily usage limits. The app uses a 512-token ceiling and 45-second GPU allocation per model call. It keeps memory and chats in server memory, isolated per visitor session. A refresh, expiration, restart, or sleep can lose them. It is not guaranteed uninterrupted hosting.

Validate local session logic without downloading cloud weights:

```powershell
.\.venv-directml\Scripts\python.exe -m unittest discover -s tests -p test_cloud_session.py -v
```
