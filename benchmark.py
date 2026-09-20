"""Check DirectML correctness, then time synchronized training updates."""
import argparse
import gc
import json
from pathlib import Path
import statistics
import time
import numpy as np
import torch
from backend import cpu_tree, is_directml, resolve_device
from config import ModelConfig, preset
from data import Corpus
from model import LucidAI
from optim import DirectMLAdamW


def verify_directml(device):
    torch.manual_seed(73)
    config = ModelConfig(vocab_size=80, context_length=32, d_model=32,
                         n_layers=2, n_heads=4, n_kv_heads=2, hidden_dim=64)
    cpu = LucidAI(config)
    gpu = LucidAI(config).to(device)
    gpu.load_state_dict(cpu.state_dict())
    x = torch.randint(0, 80, (2, 16))
    y = torch.randint(0, 80, (2, 16))
    y[:, :5] = -100
    a, loss_a, _ = cpu(x, y)
    b, loss_b, _ = gpu(x.to(device), y.to(device))
    torch.testing.assert_close(a, b.cpu(), atol=2e-5, rtol=2e-4)
    torch.testing.assert_close(loss_a, loss_b.cpu(), atol=2e-5, rtol=2e-4)
    loss_a.backward()
    loss_b.backward()
    max_gradient_error = 0.0
    for left, right in zip(cpu.parameters(), gpu.parameters()):
        difference = (left.grad - right.grad.cpu()).abs().max().item()
        max_gradient_error = max(max_gradient_error, difference)
        torch.testing.assert_close(left.grad, right.grad.cpu(), atol=2e-5, rtol=2e-3)
    cpu_opt = torch.optim.AdamW(cpu.parameters(), lr=1e-3, foreach=False)
    gpu_opt = DirectMLAdamW(gpu.parameters(), lr=1e-3, foreach=False)
    cpu_opt.step()
    gpu_opt.step()
    for left, right in zip(cpu.parameters(), gpu.parameters()):
        torch.testing.assert_close(left, right.cpu(), atol=2e-5, rtol=2e-3)
    with torch.no_grad():
        gpu.eval()
        full = gpu(x.to(device))[0]
        _, _, cache = gpu(x[:, :9].to(device), use_cache=True)
        suffix = gpu(x[:, 9:].to(device), past=cache, use_cache=True)[0]
        torch.testing.assert_close(full[:, 9:].cpu(), suffix.cpu(), atol=2e-5, rtol=2e-4)
    # Portable state must resume on DirectML, including optimizer moments.
    restored = LucidAI(config).to(device)
    restored.load_state_dict(cpu_tree(gpu.state_dict()))
    restored_opt = DirectMLAdamW(restored.parameters(), lr=1e-3)
    restored_opt.load_state_dict(cpu_tree(gpu_opt.state_dict()))
    for model, optimizer in ((gpu, gpu_opt), (restored, restored_opt)):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        model(x.to(device), y.to(device))[1].backward()
        optimizer.step()
    for left, right in zip(gpu.parameters(), restored.parameters()):
        torch.testing.assert_close(left.cpu(), right.cpu(), atol=2e-5, rtol=2e-4)
    restored.gradient_checkpointing = True
    restored_opt.zero_grad(set_to_none=True)
    restored(x.to(device), y.to(device))[1].backward()
    assert all(torch.isfinite(p.grad).all().item() for p in restored.parameters())
    return {"cpu_gpu_logits_loss_gradients": "passed", "cached_decoding": "passed",
            "optimizer_update_and_resume": "passed", "gradient_checkpointing": "passed",
            "max_gradient_absolute_error": max_gradient_error}


def measure(name, args, vocab_size):
    device = resolve_device(name)
    torch.manual_seed(1337)
    config = preset(args.preset, vocab_size)
    config.context_length = args.context
    model = LucidAI(config).to(device)
    optimizer_type = DirectMLAdamW if is_directml(device) else torch.optim.AdamW
    optimizer = optimizer_type(model.parameters(), lr=3e-4, betas=(0.9, 0.95), foreach=False)
    dataset = Corpus(Path(args.data) / "pretrain_train.bin", args.context)
    rng = np.random.default_rng(1337)
    timings, losses = [], []
    for index in range(args.warmup + args.steps):
        start = time.perf_counter()
        x, y = dataset.batch(args.batch_size, rng, device)
        optimizer.zero_grad(set_to_none=True)
        loss = model(x, y)[1]
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, foreach=False, error_if_nonfinite=True)
        optimizer.step()
        # The read synchronizes AFTER the optimizer update, not only the forward pass.
        next(model.parameters()).detach().view(-1)[0].item()
        elapsed = time.perf_counter() - start
        value = loss.item()
        if index >= args.warmup:
            timings.append(elapsed)
            losses.append(value)
        print(f"{name} step {index + 1}: {elapsed:.3f}s, loss {value:.4f}", flush=True)
    median = statistics.median(timings)
    result = {"device": name, "resolved_device": device, "preset": args.preset,
              "parameters": sum(p.numel() for p in model.parameters()),
              "context": args.context, "batch_size": args.batch_size,
              "precision": "fp32", "warmup_steps": args.warmup, "measured_steps": args.steps,
              "seconds_per_step": timings, "median_seconds_per_step": median,
              "median_tokens_per_second": args.context * args.batch_size / median, "losses": losses}
    del model, optimizer, loss, x, y
    gc.collect()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/prepared")
    parser.add_argument("--preset", choices=["tiny", "small"], default="small")
    parser.add_argument("--context", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--steps", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--out", default="runs/directml-benchmark.json")
    args = parser.parse_args()
    if min(args.context, args.batch_size, args.steps) < 1 or args.warmup < 0:
        parser.error("Context, batch and steps must be positive; warmup must be nonnegative.")
    output = Path(args.out)
    if output.exists():
        parser.error("Report already exists; choose a new --out path.")
    torch.set_num_threads(4)
    device = resolve_device("directml")
    checks = verify_directml(device)
    print(f"GPU correctness checks: {checks}", flush=True)
    metadata = json.loads((Path(args.data) / "metadata.json").read_text())
    results = [measure(name, args, metadata["vocab_size"]) for name in ("cpu", "directml")]
    import torch_directml
    report = {"torch": torch.__version__,
              "adapters": [torch_directml.device_name(i).rstrip(chr(0)) for i in range(torch_directml.device_count())],
              "checks": checks, "results": results,
              "speedup": results[0]["median_seconds_per_step"] / results[1]["median_seconds_per_step"],
              "note": "Short synchronized training benchmark, excluding validation and checkpoint I/O; not a full-training estimate."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(f"DirectML speedup: {report['speedup']:.2f}x. Report: {output.resolve()}")


if __name__ == "__main__":
    main()
