"""Explicit CPU, CUDA and optional DirectML device selection."""
import torch


def resolve_device(value):
    if value == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if value == "directml":
        try:
            import torch_directml
        except ImportError as error:
            raise RuntimeError("DirectML is not installed in this Python. Use run-directml.cmd.") from error
        if not torch_directml.is_available():
            raise RuntimeError("No DirectML GPU is available.")
        index = next((i for i in range(torch_directml.device_count())
                      if "RX 6600" in torch_directml.device_name(i)), 0)
        print(f"DirectML GPU: {torch_directml.device_name(index).rstrip(chr(0))}", flush=True)
        return str(torch_directml.device(index))
    return value


def is_directml(device):
    return str(device).startswith("privateuseone")


def cpu_tree(value):
    """Make checkpoints portable without serializing DirectML storage tags."""
    if isinstance(value, torch.Tensor):
        return value.detach().to("cpu", copy=True)
    if isinstance(value, dict):
        return {key: cpu_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [cpu_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(cpu_tree(item) for item in value)
    return value
