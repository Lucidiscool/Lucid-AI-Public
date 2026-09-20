# AMD GPU setup and measured results

**DirectML is installed and tested on this computer's AMD Radeon RX 6600 (8 GB).** The integrated AMD graphics adapter is also visible; v4 explicitly selects the RX 6600 when `--device directml` is supplied.

The isolated `.venv-directml` environment contains Python 3.12, `torch-directml 0.2.5.dev240914`, its required PyTorch 2.4.1, tokenizers 0.23.2 and NumPy 1.26.4. The original Python installation and V3 were not changed. PyTorch reports `2.4.1+cpu` and `CUDA available: False` even when DirectML is working; the DirectML adapter and tensor device are the relevant indicators.

## Use it

Open PowerShell in the v4 directory:

```powershell
.\run-directml.cmd doctor
.\run-directml.cmd test
```

GPU selection is explicit. `--device auto` still selects CUDA or CPU, so **include `--device directml` for AMD training and chat**.

To run a short, new GPU experiment on the existing starter corpus:

```powershell
.\run-directml.cmd pretrain --device directml --preset small --context 256 --steps 100 --batch-size 1 --accumulation 1 --eval-every 25 --eval-batches 2 --out checkpoints\amd-first-run
```

This is a short experiment, not sufficient training for useful English. Do not start a long run on the limited starter corpus expecting broad reasoning. Expand and finalize the dataset first, then train a fresh model/tokenizer together. The default small model's full 1,024-token context also passed a short batch-size-one benchmark on this card. Larger batch sizes and the medium preset have not been validated here.

To inspect the tested, barely-trained instruction checkpoint:

```powershell
.\run-directml.cmd chat --device directml --checkpoint checkpoints\directml-sft-test\best.pt --max-new-tokens 80
```

Its replies are not coherent yet: it received only ten pretraining updates and three instruction updates. No long training job was left running.

## Measured performance

46,150,144 parameters, FP32, batch size 1, four CPU threads, same input batches and initial weights. Timing synchronizes after the optimizer update and excludes evaluation/checkpoint I/O.

| Context | CPU median update | RX 6600 median update | Speedup | Measured updates |
|---|---:|---:|---:|---:|
| 256 tokens | 0.449 s | 0.093 s | 4.85× | 5 after 2 warmups |
| 1,024 tokens | 1.622 s | 0.465 s | 3.49× | 3 after 1 warmup |

These are short benchmarks, not promises about sustained training time. GPU compilation, other applications, temperatures and settings affect speed. The 1,024-token run still had a slower first measured update (1.026 s), so consult the individual timings rather than assuming every update takes the median.

Full machine-readable results: `runs/directml-benchmark.json` and `runs/directml-benchmark-1024.json`. To rerun without overwriting reports:

```powershell
.\run-directml.cmd benchmark --out runs\directml-benchmark-new.json
```

## What was verified

- CPU/GPU logits, masked losses and gradients agree within test tolerances; maximum gradient absolute difference in the small correctness fixture was approximately 7.45e-8.
- Cached decoding agrees with full-sequence decoding on DirectML.
- The DirectML optimizer agrees with standard AdamW, and restored optimizer/model state continues correctly.
- Gradient checkpointing completes backward with finite gradients.
- Ten real pretraining steps with the 46M model at context 256 completed: validation loss 9.8018 → 8.2314.
- Three real instruction steps with accumulation 2 completed: validation loss 9.2019 → 8.8139.
- Checkpoints save as portable CPU tensors and reload for GPU chat. Both greedy and sampled generation ran.
- Unit and CPU pipeline tests pass in both the original environment and the DirectML environment.

These checks verify execution and numerical behavior, not language quality or a long-duration stability guarantee.

## Compatibility changes

DirectML uses FP32 in this project. Validation/generation use `no_grad` because this backend fails with inference tensors in some linear operations. `DirectMLAdamW` replaces an unsupported `lerp_` operation with equivalent multiplication/addition; the original operator moved work back to the CPU. Training and the model's KV cache stay on the GPU. Token sampling runs explicitly on the CPU to avoid unsupported sampling operators. This copies one vocabulary-sized score vector per generated token.

The installed PyTorch emits a deprecation warning when gradient checkpointing calls its older CPU autocast API. It does not prevent training. Do not independently upgrade PyTorch inside this environment: DirectML pins a compatible version.

## Recreate the environment

Using an existing Python 3.12 installation, from this project directory:

```powershell
python -m venv .venv-directml
.\.venv-directml\Scripts\python.exe -m pip install -r requirements-directml.txt
```

Use a fresh environment for recreation, rather than modifying your original installation. See Microsoft's [DirectML setup documentation](https://learn.microsoft.com/en-us/windows/ai/directml/pytorch-windows) for platform details.
