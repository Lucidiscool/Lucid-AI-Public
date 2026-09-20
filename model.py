"""LucidAI v4: decoder Transformer with RoPE, GQA, SwiGLU and KV caching."""
import math
import torch
from torch import nn
from torch.nn import functional as F
from torch.utils.checkpoint import checkpoint
from config import ModelConfig
from backend import is_directml


class RMSNorm(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(width))

    def forward(self, x):
        normalized = x.float() * torch.rsqrt(x.float().square().mean(-1, keepdim=True) + 1e-5)
        return normalized.to(x.dtype) * self.weight


class Attention(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.heads, self.kv_heads = config.n_heads, config.n_kv_heads
        self.head_dim = config.d_model // config.n_heads
        self.dropout = config.dropout
        self.q = nn.Linear(config.d_model, self.heads * self.head_dim, bias=False)
        self.k = nn.Linear(config.d_model, self.kv_heads * self.head_dim, bias=False)
        self.v = nn.Linear(config.d_model, self.kv_heads * self.head_dim, bias=False)
        self.out = nn.Linear(config.d_model, config.d_model, bias=False)
        inv = 1 / config.rope_theta ** (torch.arange(0, self.head_dim, 2).float() / self.head_dim)
        angles = torch.outer(torch.arange(config.context_length).float(), inv)
        self.register_buffer("cos", angles.cos(), persistent=False)
        self.register_buffer("sin", angles.sin(), persistent=False)

    def rotate(self, x, offset):
        length = x.shape[-2]
        cos = self.cos[offset:offset + length].to(x.dtype)
        sin = self.sin[offset:offset + length].to(x.dtype)
        even, odd = x[..., 0::2], x[..., 1::2]
        return torch.stack((even * cos - odd * sin, even * sin + odd * cos), -1).flatten(-2)

    def forward(self, x, past=None, use_cache=False):
        b, t, _ = x.shape
        offset = 0 if past is None else past[0].shape[-2]
        q = self.rotate(self.q(x).view(b, t, self.heads, self.head_dim).transpose(1, 2), offset)
        k = self.rotate(self.k(x).view(b, t, self.kv_heads, self.head_dim).transpose(1, 2), offset)
        v = self.v(x).view(b, t, self.kv_heads, self.head_dim).transpose(1, 2)
        if past is not None:
            k, v = torch.cat((past[0], k), -2), torch.cat((past[1], v), -2)
        cache = (k, v) if use_cache else None
        k = k.repeat_interleave(self.heads // self.kv_heads, dim=1)
        v = v.repeat_interleave(self.heads // self.kv_heads, dim=1)
        # With cached keys, the query is aligned to the END of the key sequence.
        mask = None
        if offset:
            mask = torch.arange(k.shape[-2], device=x.device)[None, :] <= (
                offset + torch.arange(t, device=x.device)[:, None])
        result = F.scaled_dot_product_attention(q, k, v, attn_mask=mask,
            is_causal=not offset, dropout_p=self.dropout if self.training else 0.0)
        return self.out(result.transpose(1, 2).contiguous().view(b, t, -1)), cache


class Block(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.attention_norm = RMSNorm(config.d_model)
        self.attention = Attention(config)
        self.ffn_norm = RMSNorm(config.d_model)
        self.gate = nn.Linear(config.d_model, config.hidden_dim, bias=False)
        self.up = nn.Linear(config.d_model, config.hidden_dim, bias=False)
        self.down = nn.Linear(config.hidden_dim, config.d_model, bias=False)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x, past=None, use_cache=False):
        attention, cache = self.attention(self.attention_norm(x), past, use_cache)
        x = x + self.dropout(attention)
        normalized = self.ffn_norm(x)
        x = x + self.dropout(self.down(F.silu(self.gate(normalized)) * self.up(normalized)))
        return x, cache


class LucidAI(nn.Module):
    def __init__(self, config: ModelConfig):
        super().__init__()
        config.validate()
        self.config = config
        self.gradient_checkpointing = False
        self.embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.blocks = nn.ModuleList([Block(config) for _ in range(config.n_layers)])
        self.norm = RMSNorm(config.d_model)
        self.apply(self.initialize)
        for block in self.blocks:
            for layer in (block.attention.out, block.down):
                nn.init.normal_(layer.weight, std=0.02 / math.sqrt(2 * config.n_layers))

    @staticmethod
    def initialize(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, std=0.02)

    def forward(self, input_ids, targets=None, past=None, use_cache=False, last_token_only=False):
        if last_token_only and targets is not None:
            raise ValueError("Training loss requires logits for every token.")
        offset = 0 if past is None else past[0][0].shape[-2]
        if input_ids.shape[1] + offset > self.config.context_length:
            raise ValueError("Input and cached tokens exceed the model context length.")
        if use_cache and self.training and self.gradient_checkpointing:
            raise ValueError("Caching is unavailable with gradient checkpointing during training.")
        x, caches = self.embedding(input_ids), []
        for index, block in enumerate(self.blocks):
            if self.gradient_checkpointing and self.training:
                x = checkpoint(lambda y, layer=block: layer(y)[0], x, use_reentrant=False)
            else:
                x, cache = block(x, None if past is None else past[index], use_cache)
                caches.append(cache)
        # Prefill needs all hidden states for the cache, but only the final
        # vocabulary projection for sampling. Avoid allocating T x vocabulary.
        logits = F.linear(self.norm(x[:, -1:] if last_token_only else x), self.embedding.weight)
        loss = None
        if targets is not None:
            if not (targets != -100).any():
                raise ValueError("Batch has no supervised tokens.")
            loss = F.cross_entropy(logits.float().reshape(-1, self.config.vocab_size),
                                   targets.reshape(-1), ignore_index=-100)
        return logits, loss, caches if use_cache else None

    @torch.no_grad()
    def generate(self, ids, max_new_tokens=160, temperature=0.7, top_p=0.9,
                 repetition_penalty=1.1, stop_ids=(), banned_ids=()):
        """Single-conversation generation; stop before exceeding trained context."""
        if ids.ndim != 2 or ids.shape[0] != 1 or ids.shape[1] < 1:
            raise ValueError("Generation requires one nonempty conversation.")
        if (not math.isfinite(temperature) or temperature < 0 or not 0 < top_p <= 1
                or not math.isfinite(repetition_penalty) or repetition_penalty < 1):
            raise ValueError("Invalid sampling settings.")
        if max_new_tokens < 1 or ids.shape[1] > self.config.context_length:
            raise ValueError("Use a positive token limit and a prompt within the model context.")
        if any(i < 0 or i >= self.config.vocab_size for i in (*stop_ids, *banned_ids)):
            raise ValueError("Sampling token IDs must be inside the vocabulary.")
        if len(set(banned_ids)) >= self.config.vocab_size:
            raise ValueError("At least one vocabulary token must remain available.")
        self.eval()
        past, current = None, ids
        for _ in range(min(max_new_tokens, self.config.context_length - ids.shape[1])):
            logits, _, past = self(current, past=past, use_cache=True, last_token_only=True)
            scores = logits[:, -1].float()
            # Sampling is small and CPU-based on DirectML; model and cache stay on GPU.
            sampling_ids = ids
            if is_directml(ids.device):
                scores, sampling_ids = scores.cpu(), ids.cpu()
            seen = torch.unique(sampling_ids)
            scores[:, seen] = torch.where(scores[:, seen] < 0,
                scores[:, seen] * repetition_penalty, scores[:, seen] / repetition_penalty)
            scores[:, list(banned_ids)] = -float("inf")
            if temperature == 0:
                token = scores.argmax(-1, keepdim=True)
            else:
                scores /= temperature
                ordered, indices = scores.sort(descending=True)
                remove = ordered.softmax(-1).cumsum(-1) > top_p
                remove[:, 1:] = remove[:, :-1].clone()
                remove[:, 0] = False
                ordered.masked_fill_(remove, -float("inf"))
                selected = torch.multinomial(ordered.softmax(-1), 1)
                token = indices.gather(-1, selected)
            token = token.to(ids.device)
            ids = torch.cat((ids, token), dim=1)
            if token.item() in stop_ids:
                break
            current = token
        return ids
