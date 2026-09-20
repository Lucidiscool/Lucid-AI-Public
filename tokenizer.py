"""A byte-level BPE trained only on the training partition."""
import hashlib
from pathlib import Path
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

SPECIAL = ["<|pad|>", "<|unk|>", "<|bos|>", "<|eos|>",
           "<|system|>", "<|user|>", "<|assistant|>"]


def train_tokenizer(texts, path, vocab_size):
    tokenizer = Tokenizer(models.BPE(unk_token="<|unk|>"))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    tokenizer.train_from_iterator(texts, trainers.BpeTrainer(vocab_size=vocab_size,
        min_frequency=2, special_tokens=SPECIAL, initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    tokenizer.save(str(path))
    return tokenizer


def load_tokenizer(path):
    tokenizer = Tokenizer.from_file(str(path))
    if any(tokenizer.token_to_id(token) is None for token in SPECIAL):
        raise ValueError("Tokenizer is missing required conversation tokens.")
    return tokenizer


def fingerprint(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def encode_text(tokenizer, text):
    # Literal role delimiters in user documents must not become structural tokens.
    for special in SPECIAL:
        text = text.replace(special, special.replace("<|", "< |"))
    return tokenizer.encode(text).ids


def encode_messages(tokenizer, messages):
    """Mask prompts; supervise assistant text AND its end-of-turn token."""
    ids, labels = [tokenizer.token_to_id("<|bos|>")], [-100]
    for message in messages:
        role = message["role"]
        part = [tokenizer.token_to_id(f"<|{role}|>")]
        content = encode_text(tokenizer, message["content"]) + [tokenizer.token_to_id("<|eos|>")]
        ids.extend(part + content)
        labels.extend([-100] + (content if role == "assistant" else [-100] * len(content)))
    return ids, labels
