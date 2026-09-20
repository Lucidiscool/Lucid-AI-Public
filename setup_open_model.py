"""Install a pinned local llama.cpp runtime and checksum-verified GGUF."""
import hashlib
import json
from pathlib import Path
import time
import zipfile
import httpx

ROOT = Path(__file__).resolve().parent


def sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download(client, url, path, expected_hash, expected_size):
    if path.exists() and path.stat().st_size == expected_size and sha256(path) == expected_hash:
        print(f"Verified existing {path.name}", flush=True)
        return
    partial = path.with_suffix(path.suffix + ".partial")
    for attempt in range(4):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset < expected_size:
                with client.stream("GET", url, headers={"Range": f"bytes={offset}-"} if offset else {}) as response:
                    response.raise_for_status()
                    if offset and response.status_code != 206:
                        offset = 0
                    if response.status_code == 206 and not response.headers.get("content-range", "").startswith(f"bytes {offset}-"):
                        raise ValueError("Unexpected download range")
                    count, last = offset, time.monotonic()
                    with partial.open("ab" if offset else "wb") as stream:
                        for chunk in response.iter_bytes(1024 * 1024):
                            stream.write(chunk)
                            count += len(chunk)
                            if count > expected_size:
                                raise ValueError("Download larger than publisher manifest")
                            if time.monotonic() - last > 2:
                                print(f"{path.name}: {count / 1e6:.0f}/{expected_size / 1e6:.0f} MB ({100 * count / expected_size:.1f}%)", flush=True)
                                last = time.monotonic()
            print(f"Checking SHA-256 for {path.name}...", flush=True)
            if partial.stat().st_size != expected_size or sha256(partial) != expected_hash:
                raise ValueError("Downloaded file failed size/hash verification")
            partial.replace(path)
            print(f"Verified {path.name}", flush=True)
            return
        except (httpx.HTTPError, OSError) as error:
            if attempt == 3:
                raise
            print(f"Download interrupted: {error}; retrying.", flush=True)
            time.sleep(2)


def main():
    sources = json.loads((ROOT / "runs/local-model-sources.json").read_text(encoding="utf-8"))
    repo = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
    model_info = sources[repo]
    file = next(f for f in model_info["files"] if f["rfilename"].endswith(".gguf"))
    asset = sources["runtime"]["assets"][0]
    runtime = ROOT / "runtime" / sources["runtime"]["tag"]
    models = ROOT / "models"
    runtime.mkdir(parents=True, exist_ok=True)
    models.mkdir(exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(120, connect=30)) as client:
        archive = runtime / asset["name"]
        download(client, asset["browser_download_url"], archive, asset["digest"].split(":")[1], asset["size"])
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                target = (runtime / member.filename).resolve()
                if not target.is_relative_to(runtime.resolve()):
                    raise ValueError("Unsafe archive path")
            package.extractall(runtime)
        model = models / file["rfilename"]
        model_url = f"https://huggingface.co/{repo}/resolve/{model_info['sha']}/{file['rfilename']}"
        download(client, model_url, model, file["lfs"]["sha256"], file["size"])
        for name, url in {
            "MODEL_CARD.md": f"https://huggingface.co/{repo}/resolve/{model_info['sha']}/README.md",
            "LICENSE-QWEN.txt": "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/main/LICENSE",
        }.items():
            response = client.get(url)
            response.raise_for_status()
            (models / name).write_bytes(response.content)
    executable = next(runtime.rglob("llama-server.exe"))
    config = {"model_name": "Qwen3-4B-Instruct-2507", "alias": "lucid-local",
              "model": str(model), "model_sha256": file["lfs"]["sha256"], "model_bytes": file["size"],
              "model_repository": repo, "model_revision": model_info["sha"],
              "server": str(executable), "runtime_version": sources["runtime"]["tag"],
              "host": "127.0.0.1", "port": 8097, "context": 8192, "gpu_layers": 99}
    (ROOT / "local_model.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Installation verified. Ready for GPU server tests.", flush=True)


if __name__ == "__main__":
    main()
