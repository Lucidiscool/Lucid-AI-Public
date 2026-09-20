"""Architecture presets. No pretrained weights or external model APIs."""
from dataclasses import asdict, dataclass


@dataclass
class ModelConfig:
    vocab_size: int = 16384
    context_length: int = 1024
    d_model: int = 512
    n_layers: int = 12
    n_heads: int = 8
    n_kv_heads: int = 4
    hidden_dim: int = 1536
    dropout: float = 0.0
    rope_theta: float = 10000.0

    def validate(self):
        if min(self.vocab_size, self.context_length, self.d_model, self.n_layers,
               self.n_heads, self.n_kv_heads, self.hidden_dim) < 1:
            raise ValueError("All architecture dimensions must be positive.")
        if self.d_model % self.n_heads or (self.d_model // self.n_heads) % 2:
            raise ValueError("Heads must divide model width and have an even dimension.")
        if self.n_heads % self.n_kv_heads:
            raise ValueError("KV heads must divide attention heads.")
        if not 0 <= self.dropout < 1:
            raise ValueError("Dropout must be in [0, 1).")

    def to_dict(self):
        return asdict(self)


def preset(name, vocab_size=16384):
    sizes = {
        "tiny": dict(d_model=128, n_layers=4, n_heads=4, n_kv_heads=2,
                     hidden_dim=384, context_length=256),
        "small": {},
        "medium": dict(d_model=768, n_layers=16, n_heads=12, n_kv_heads=4,
                       hidden_dim=2304, context_length=2048),
    }
    config = ModelConfig(vocab_size=vocab_size, **sizes[name])
    config.validate()
    return config
