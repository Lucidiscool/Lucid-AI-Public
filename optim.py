"""AdamW using primitive tensor operations supported by DirectML."""
import math
import torch


class DirectMLAdamW(torch.optim.AdamW):
    @torch.no_grad()
    def step(self, closure=None):
        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()
        for group in self.param_groups:
            if group.get("amsgrad") or group.get("maximize") or group.get("capturable") or group.get("differentiable"):
                raise ValueError("DirectMLAdamW supports standard, non-capturable AdamW only.")
            beta1, beta2 = group["betas"]
            for parameter in group["params"]:
                if parameter.grad is None:
                    continue
                gradient = parameter.grad
                if gradient.is_sparse:
                    raise ValueError("Sparse gradients are not supported.")
                state = self.state[parameter]
                if not state:
                    state["step"] = torch.tensor(0.0, device="cpu")
                    state["exp_avg"] = torch.zeros_like(parameter)
                    state["exp_avg_sq"] = torch.zeros_like(parameter)
                state["step"] += 1
                step = state["step"].item()
                average, square = state["exp_avg"], state["exp_avg_sq"]
                parameter.mul_(1 - group["lr"] * group["weight_decay"])
                # torch AdamW's lerp_ falls back to CPU in DirectML 0.2.5.
                average.mul_(beta1).add_(gradient, alpha=1 - beta1)
                square.mul_(beta2).addcmul_(gradient, gradient, value=1 - beta2)
                denominator = square.sqrt().div_(math.sqrt(1 - beta2 ** step)).add_(group["eps"])
                parameter.addcdiv_(average, denominator, value=-group["lr"] / (1 - beta1 ** step))
        return loss
