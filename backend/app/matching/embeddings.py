"""
Encoders for FindIt Campus.

Text  -> Sentence-Transformers (all-MiniLM-L6-v2): fast, 384-dim, great for
         short free-text descriptions like "black wallet with cards".
Image -> CLIP (via open_clip): 512-dim, matches a photo against *text* too,
         but here we use it to compare photo-vs-photo across multiple images
         per report (a report can have >1 photo).

Both encoders are loaded once (lazy singletons) and reused across requests --
loading a transformer model per-request would make the API unusably slow.
"""

from functools import lru_cache
from typing import List

import numpy as np
from PIL import Image


@lru_cache(maxsize=1)
def _text_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _image_model():
    import open_clip
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="openai"
    )
    model.eval()
    return model, preprocess


def encode_text(description: str) -> np.ndarray:
    """Returns a normalized 384-dim vector for a lost/found description."""
    if not description or not description.strip():
        return None
    vec = _text_model().encode(description, normalize_embeddings=True)
    return vec


def encode_images(image_paths: List[str]) -> np.ndarray:
    """
    Aggregates multiple photos of one report into a single normalized
    512-dim vector (mean-pooling). Mean-pooling is a deliberate choice:
    a report might have a blurry photo and a clear one -- averaging is
    more robust than picking "the best" photo, which needs its own model.
    """
    import torch

    if not image_paths:
        return None

    model, preprocess = _image_model()
    vecs = []
    with torch.no_grad():
        for path in image_paths:
            img = preprocess(Image.open(path).convert("RGB")).unsqueeze(0)
            feat = model.encode_image(img)
            feat = feat / feat.norm(dim=-1, keepdim=True)
            vecs.append(feat.squeeze(0).numpy())

    return np.mean(vecs, axis=0)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return None
    a, b = np.asarray(a), np.asarray(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)