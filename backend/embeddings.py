"""Turns text into embedding vectors using a small local model.

An embedding is a list of numbers representing the *meaning* of a piece of
text - similar meanings end up as nearby vectors, so we can find relevant
transcript chunks for a question by comparing vectors instead of matching
keywords. Runs entirely on your own CPU: no API call, no extra key, free.
First run downloads the model (~90MB) from Hugging Face; cached after that.
"""

from typing import Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from . import config

# Keeps PyTorch's intra-op thread pool (and its per-thread working buffers)
# from scaling up with the host's CPU count - matters on small, memory-
# capped hosting instances more than it matters for raw speed here.
torch.set_num_threads(1)

_model: Optional[SentenceTransformer] = None

# Small encode batches cap the peak memory PyTorch allocates per call.
# PyTorch's allocator doesn't hand freed memory back to the OS, so this
# peak effectively becomes the process's new memory floor - worth keeping
# low on a memory-constrained host even though it's not the fastest option.
_ENCODE_BATCH_SIZE = 8


def get_embedder() -> SentenceTransformer:
    """Loads the embedding model once and reuses it - loading takes a few
    seconds, so we don't want to redo it on every request."""
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embeds a batch of chunk texts. Returns shape (len(texts), 384).

    normalize_embeddings=True scales every vector to length 1, which is what
    lets vectorstore.py compute cosine similarity as a plain dot product
    instead of the full cosine formula - same result, cheaper to compute.
    """
    model = get_embedder()
    return model.encode(texts, normalize_embeddings=True, batch_size=_ENCODE_BATCH_SIZE)


def embed_query(text: str) -> np.ndarray:
    """Embeds a single question - same function, batch of one."""
    return embed_texts([text])[0]


if __name__ == "__main__":
    # Smoke test: python -m backend.embeddings
    texts = [
        "The cat sat on the mat.",
        "A feline was resting on the rug.",
        "The stock market crashed yesterday.",
    ]
    vectors = embed_texts(texts)
    print("shape:", vectors.shape)

    sim_cat_feline = float(vectors[0] @ vectors[1])
    sim_cat_stocks = float(vectors[0] @ vectors[2])
    print(f"similarity(cat, feline) = {sim_cat_feline:.3f}  (should be high - same meaning)")
    print(f"similarity(cat, stocks) = {sim_cat_stocks:.3f}  (should be low - unrelated)")
