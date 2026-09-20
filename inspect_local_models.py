import json
from pathlib import Path
import httpx

with httpx.Client(timeout=30, follow_redirects=True) as client:
    result = {}
    for name in ("Qwen/Qwen3-4B-Instruct-2507-GGUF", "unsloth/Qwen3-4B-Instruct-2507-GGUF"):
        response = client.get("https://huggingface.co/api/models/" + name, params={"blobs": "true"})
        if response.status_code == 200:
            row = response.json()
            result[name] = {"sha": row["sha"], "cardData": row.get("cardData"),
                            "files": [f for f in row["siblings"] if "Q4_K_M" in f["rfilename"] or f["rfilename"] in ("README.md", "LICENSE")]}
    release = client.get("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest")
    release.raise_for_status()
    row = release.json()
    result["runtime"] = {"tag": row["tag_name"], "assets": [a for a in row["assets"] if "win-vulkan-x64.zip" in a["name"]]}
    Path("runs/local-model-sources.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
