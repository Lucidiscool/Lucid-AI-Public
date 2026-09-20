"""Two-stage training from scratch, with resumable atomic checkpoints."""
import argparse
from contextlib import nullcontext
import json
import math
from pathlib import Path
import random
import signal
import time
import numpy as np
import torch
from config import ModelConfig, preset
from data import load_data
from model import LucidAI
from tokenizer import fingerprint, load_tokenizer
from backend import resolve_device, is_directml, cpu_tree
from optim import DirectMLAdamW


def replace_with_retry(temporary, path):
    """Windows readers/scanners may briefly hold the destination open."""
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * 2 ** attempt)


def atomic_save(payload, path):
    temporary = path.with_suffix(".tmp")
    torch.save(cpu_tree(payload), temporary)
    replace_with_retry(temporary, path)


def load_checkpoint(path):
    return torch.load(path, map_location="cpu", weights_only=True)


def learning_rate(step, steps, peak, warmup):
    if step < warmup:
        return peak * (step + 1) / max(warmup, 1)
    progress = min((step - warmup) / max(steps - warmup - 1, 1), 1)
    return peak * (0.1 + 0.9 * (1 + math.cos(math.pi * progress)) / 2)


@torch.no_grad()
def evaluate(model, dataset, batch_size, batches, device, amp):
    model.eval()
    rng, total, tokens = np.random.default_rng(8675309), 0.0, 0
    for _ in range(batches):
        x, y = dataset.batch(batch_size, rng, device)
        with amp():
            _, loss, _ = model(x, y)
        count = (y != -100).sum().item()
        total += loss.item() * count
        tokens += count
    model.train()
    result = total / tokens
    if not math.isfinite(result):
        raise FloatingPointError("Non-finite validation loss.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["pretrain", "sft"])
    parser.add_argument("--data", default="data/prepared")
    parser.add_argument("--out", help="Defaults to checkpoints/<stage>")
    parser.add_argument("--preset", choices=["tiny", "small", "medium"], default="small")
    parser.add_argument("--context", type=int, help="Override context for a NEW model only")
    parser.add_argument("--init", help="Start a new schedule from v4 weights (fresh optimizer); also required for new SFT")
    parser.add_argument("--resume", help="Resume this stage including optimizer and RNG state")
    parser.add_argument("--steps", type=int, default=20000, help="Total optimizer steps, including resumed steps")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--accumulation", type=int, default=16)
    parser.add_argument("--lr", type=float, help="Defaults: pretrain=3e-4, SFT=3e-5")
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--eval-every", type=int, default=250)
    parser.add_argument("--eval-batches", type=int, default=20)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda", "directml"], default="auto")
    parser.add_argument("--precision", choices=["auto", "fp32", "bf16", "fp16"], default="auto")
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--stop-file", help="Pause safely after a complete update when this file exists.")
    parser.add_argument("--max-run-minutes", type=float, help="Pause this session without changing the full LR schedule.")
    args = parser.parse_args()
    if min(args.steps, args.batch_size, args.accumulation, args.eval_every, args.eval_batches, args.threads) < 1:
        parser.error("Step, batch, accumulation, evaluation and thread counts must be positive.")
    if args.warmup < 0 or (args.lr is not None and args.lr <= 0):
        parser.error("Warmup must be nonnegative and learning rate positive.")
    if args.max_run_minutes is not None and args.max_run_minutes <= 0:
        parser.error("--max-run-minutes must be positive.")
    if args.init and args.resume:
        parser.error("Choose --init OR --resume.")
    if args.stage == "sft" and not (args.init or args.resume):
        parser.error("SFT requires --init from your pretrained v4 model or --resume.")
    torch.set_num_threads(args.threads)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = resolve_device(args.device)
    precision = args.precision
    if precision == "auto":
        precision = ("bf16" if torch.cuda.is_bf16_supported() else "fp16") if device == "cuda" else "fp32"
    if device != "cuda" and precision != "fp32":
        parser.error("Use fp32 on CPU/DirectML; mixed precision is supported here on CUDA.")
    dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[precision]
    amp = (lambda: torch.autocast(device_type=device, dtype=dtype)) if precision != "fp32" else nullcontext
    scaler = torch.amp.GradScaler("cuda", enabled=precision == "fp16")
    directory = Path(args.data)
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for name, expected_hash in metadata["files"].items():
        if fingerprint(directory / name) != expected_hash:
            raise ValueError(f"Prepared file {name} changed. Prepare a new dataset.")
    tokenizer_path = directory / "tokenizer.json"
    tokenizer_hash = fingerprint(tokenizer_path)
    if metadata["tokenizer_sha256"] != tokenizer_hash:
        raise ValueError("Tokenizer changed after data preparation. Prepare a new dataset.")
    tokenizer = load_tokenizer(tokenizer_path)
    saved = load_checkpoint(args.resume or args.init) if args.resume or args.init else None
    if saved:
        if args.init and args.stage == "pretrain" and saved["stage"] != "pretrain":
            parser.error("Continued pretraining requires a pretrain checkpoint.")
        if saved["tokenizer_sha256"] != tokenizer_hash:
            raise ValueError("Checkpoint and dataset tokenizers do not match.")
        config = ModelConfig(**saved["config"])
        if args.context is not None and args.context != config.context_length:
            parser.error("Context cannot change when loading weights.")
    else:
        config = preset(args.preset, tokenizer.get_vocab_size())
        if args.context is not None:
            config.context_length = args.context
    output = Path(args.out or f"checkpoints/{args.stage}")
    output.mkdir(parents=True, exist_ok=True)
    if not args.resume and any(output.iterdir()):
        raise ValueError(f"Refusing to overwrite {output}; use --resume or a new --out directory.")
    tokenizer.save(str(output / "tokenizer.json"))
    model = LucidAI(config).to(device)
    model.gradient_checkpointing = args.gradient_checkpointing
    if saved:
        model.load_state_dict(saved["model"])
    lr = args.lr if args.lr is not None else (3e-4 if args.stage == "pretrain" else 3e-5)
    optimizer_type = DirectMLAdamW if is_directml(device) else torch.optim.AdamW
    optimizer = optimizer_type([
        {"params": [p for p in model.parameters() if p.ndim >= 2], "weight_decay": 0.1},
        {"params": [p for p in model.parameters() if p.ndim < 2], "weight_decay": 0.0},
    ], lr=lr, betas=(0.9, 0.95), foreach=False if is_directml(device) else None)
    rng, start, best = np.random.default_rng(args.seed), 0, float("inf")
    if args.resume:
        if saved["stage"] != args.stage or saved["data_sha256"] != fingerprint(metadata_path):
            raise ValueError("Resume requires the same stage and prepared dataset.")
        optimizer.load_state_dict(saved["optimizer"])
        scaler.load_state_dict(saved["scaler"])
        rng.bit_generator.state = saved["rng"]
        torch.set_rng_state(saved["torch_rng"])
        if device == "cuda" and saved["cuda_rng"] is not None:
            torch.cuda.set_rng_state_all(saved["cuda_rng"])
        start, best = saved["step"], saved["best_val_loss"]
        for name in ("batch_size", "accumulation", "warmup", "steps", "gradient_checkpointing"):
            if getattr(args, name) != saved["settings"][name]:
                parser.error(f"Exact resume requires original --{name.replace('_', '-')}={saved['settings'][name]}.")
        if lr != saved["peak_lr"] or precision != saved["precision"]:
            parser.error("Resume requires the original learning rate and precision.")
    train_data, val_data = load_data(directory, args.stage, config.context_length,
                                    tokenizer.token_to_id("<|pad|>"))
    print(f"LucidAI v4 | {sum(p.numel() for p in model.parameters()):,} parameters | {device} {precision}", flush=True)
    print(f"Context {config.context_length}; effective batch {args.batch_size * args.accumulation}", flush=True)
    if device == "cpu":
        print("CPU mode: suitable for smoke tests; substantial training will be slow.", flush=True)
    completed = start
    started = time.monotonic()
    elapsed_before = saved.get("elapsed_seconds", 0.0) if args.resume else 0.0
    trained_tokens = saved.get("trained_tokens", 0) if args.resume else 0
    last_val = saved.get("last_val_loss", best) if args.resume else None
    stop_requested = False

    def status(state, error=None):
        elapsed = time.monotonic() - started
        per_step = elapsed / (completed - start) if completed > start else None
        row = {"state": state, "stage": args.stage, "completed_step": completed,
               "total_steps": args.steps, "last_val_loss": last_val,
               "best_val_loss": best if math.isfinite(best) else None,
               "trained_tokens": trained_tokens, "device": args.device,
               "elapsed_seconds": elapsed + elapsed_before, "seconds_per_step": per_step,
               "eta_seconds": per_step * (args.steps - completed) if per_step else None,
               "updated_at": time.time(), "error": error}
        temporary = output / "status.tmp"
        try:
            temporary.write_text(json.dumps(row, indent=2, allow_nan=False), encoding="utf-8")
            replace_with_retry(temporary, output / "status.json")
        except OSError as status_error:
            # Telemetry failure must not discard otherwise healthy training.
            # Checkpoint saves remain mandatory and still raise on failure.
            print(f"Warning: progress file update failed: {status_error}", flush=True)

    def request_stop(signum, frame):
        nonlocal stop_requested
        stop_requested = True
        print("Pause requested; finishing the current update before saving.", flush=True)

    previous_sigint = signal.signal(signal.SIGINT, request_stop)

    def save(name):
        atomic_save({"format_version": 4, "config": config.to_dict(), "model": model.state_dict(),
            "optimizer": optimizer.state_dict(), "scaler": scaler.state_dict(), "step": completed,
            "stage": args.stage, "best_val_loss": best, "rng": rng.bit_generator.state,
            "torch_rng": torch.get_rng_state(),
            "cuda_rng": torch.cuda.get_rng_state_all() if device == "cuda" else None,
            "tokenizer_sha256": tokenizer_hash, "data_sha256": fingerprint(metadata_path),
            "settings": vars(args), "peak_lr": lr, "precision": precision,
            "trained_tokens": trained_tokens, "last_val_loss": last_val,
            "elapsed_seconds": elapsed_before + time.monotonic() - started}, output / name)
        # Keep progress in the checkpoint for a new process to continue reporting.

    try:
        if not args.resume:
            best = evaluate(model, val_data, args.batch_size, args.eval_batches, device, amp)
            last_val = best
            print(f"Initial validation loss: {best:.4f}", flush=True)
            save("best.pt")
        status("running")
        while completed < args.steps:
            if (stop_requested or (args.stop_file and Path(args.stop_file).exists())
                    or (args.max_run_minutes is not None and
                        time.monotonic() - started >= args.max_run_minutes * 60)):
                save("latest.pt")
                status("paused")
                print(f"Paused safely at step {completed}.", flush=True)
                break
            step = completed
            model.train()
            optimizer.zero_grad(set_to_none=True)
            batches = [train_data.batch(args.batch_size, rng, device) for _ in range(args.accumulation)]
            token_count = sum((y != -100).sum().item() for _, y in batches)
            train_loss = 0.0
            for x, y in batches:
                weight = (y != -100).sum().item() / token_count
                with amp():
                    _, loss, _ = model(x, y)
                if not torch.isfinite(loss):
                    raise FloatingPointError("Non-finite loss; training stopped before saving damaged weights.")
                train_loss += loss.item() * weight
                scaler.scale(loss * weight).backward()
            scaler.unscale_(optimizer)
            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0,
                error_if_nonfinite=precision != "fp16", foreach=False if is_directml(device) else None)
            if precision == "fp16" and not torch.isfinite(grad_norm):
                # GradScaler recorded overflow during unscale_. Reduce its scale
                # and retry without counting or applying a damaged optimizer update.
                scaler.update()
                print("FP16 gradient overflow: reduced loss scale; retrying update.", flush=True)
                continue
            rate = learning_rate(step, args.steps, lr, min(args.warmup, args.steps // 10))
            for group in optimizer.param_groups:
                group["lr"] = rate
            scaler.step(optimizer)
            scaler.update()
            completed = step + 1
            trained_tokens += token_count
            if completed % 10 == 0 or completed == 1:
                print(f"step {completed}/{args.steps} loss={train_loss:.4f} lr={rate:.2e}", flush=True)
            if completed % args.eval_every == 0 or completed == args.steps:
                val = evaluate(model, val_data, args.batch_size, args.eval_batches, device, amp)
                last_val = val
                improved = val < best
                best = min(best, val)
                row = {"step": completed, "train_loss": train_loss, "val_loss": val,
                       "perplexity": math.exp(min(val, 20)), "lr": rate,
                       "grad_norm": float(grad_norm), "elapsed_seconds": time.monotonic() - started}
                with (output / "metrics.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row) + "\n")
                save("latest.pt")
                if improved:
                    save("best.pt")
                print(f"validation={val:.4f} best={best:.4f} saved step {completed}", flush=True)
            status("running")
        else:
            status("completed")
    except KeyboardInterrupt:
        status("interrupted", "Interrupted outside the safe pause handler; use the last saved checkpoint.")
        raise
    except Exception as error:
        status("failed", str(error))
        raise
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
    print(f"Checkpoint directory: {output.resolve()}")


if __name__ == "__main__":
    main()
