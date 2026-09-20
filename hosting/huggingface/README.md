---
title: Lucid AI V5
emoji: ✨
colorFrom: yellow
colorTo: gray
sdk: gradio
sdk_version: 6.28.0
python_version: '3.12'
app_file: app.py
pinned: false
license: apache-2.0
short_description: Lucid V5 on free GPUs, powered by Qwen3-4B-Instruct-2507
---

# Lucid AI V5

Uses the original Lucid V5 DeveloperChat, memory, feedback, and experimental-mode code from https://github.com/Lucidiscool/Lucid-AI-Public.

The cloud adapter runs the same underlying Qwen3-4B-Instruct-2507 model using Transformers BF16 on ZeroGPU, instead of the Windows llama.cpp Q4 GGUF runtime. Responses can differ because of numeric precision and sampling. No paid inference API is used.

Each Gradio session has separate in-memory chats and memories. Sessions are temporary and subject to Gradio expiration, Space restarts, GPU queues, and per-visitor daily quotas. Public web research is disabled. The owner's local computer and private workspace are not used.
