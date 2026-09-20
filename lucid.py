"""One entry point for LucidAI v4. All paths resolve from this project."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "help"
    options = sys.argv[2:]
    scripts = {"prepare": "prepare.py", "chat": "dev_chat.py", "chat-scratch": "chat.py", "evaluate": "evaluate.py",
               "benchmark": "benchmark.py", "status": "status.py", "collect": "collect_data.py"}
    if command == "chat" and any(option.startswith("--checkpoint") for option in options):
        scripts["chat"] = "chat.py"
    if command in scripts:
        return subprocess.call([sys.executable, str(ROOT / scripts[command]), *options], cwd=ROOT)
    if command in ("pretrain", "sft"):
        return subprocess.call([sys.executable, str(ROOT / "train.py"), command, *options], cwd=ROOT)
    if command == "test":
        return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT)
    if command == "doctor":
        import torch
        import tokenizers
        from config import preset
        from model import LucidAI
        print(f"Python: {sys.executable}\nPyTorch: {torch.__version__}\nTokenizers: {tokenizers.__version__}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"GPU: {torch.cuda.get_device_name()}")
        try:
            import torch_directml
            for index in range(torch_directml.device_count()):
                print(f"DirectML adapter {index}: {torch_directml.device_name(index).rstrip(chr(0))}")
            print("Select your AMD GPU with --device directml.")
        except ImportError:
            print("DirectML: not installed in this environment.")
        for name in ("tiny", "small", "medium"):
            config = preset(name)
            with torch.device("meta"):
                model = LucidAI(config)
            print(f"{name}: {sum(p.numel() for p in model.parameters()):,} parameters, {config.context_length} context")
        print("Prepared data:", (ROOT / "data/prepared/metadata.json").exists())
        print("Trained SFT checkpoint:", (ROOT / "checkpoints/sft/best.pt").exists())
        return 0
    print("LucidAI v4 — local Qwen chat and from-scratch experiments\n")
    print("run.cmd doctor                  Check Python, GPU and model sizes")
    print("run.cmd prepare --help          Prepare data and train tokenizer")
    print("run.cmd pretrain --help         Learn language from raw text")
    print("run.cmd sft --help              Learn how to answer instructions")
    print("run.cmd chat                    Chat with local Qwen")
    print("run.cmd chat-scratch            Chat with the from-scratch model")
    print("run.cmd evaluate                Generate answers for human review")
    print("run.cmd test                    Run correctness and pipeline tests")
    print("run.cmd status                  Show training progress without loading weights")
    print("run.cmd collect --help          Collect revision-pinned training sources")
    print("\nStart with OPEN_WEIGHT.md. Default chat uses pretrained Qwen weights locally.")
    return 0 if command == "help" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModuleNotFoundError as error:
        print(f"Missing dependency: {error.name}. Install requirements.txt with your Python interpreter.", file=sys.stderr)
        raise SystemExit(1)
