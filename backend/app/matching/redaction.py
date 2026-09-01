"""
Photo redaction for high-risk FOUND items (ID cards, phones, academic
documents -- see HIGH_RISK_CATEGORIES in models/report.py).

Why this exists: a found ID card's photo, posted publicly before its owner
claims it, can leak a name/photo/roll number to anyone browsing the site --
exactly the kind of exposure your abstract calls out. So for high-risk
reports we keep two copies of every photo on disk:

  uploads/<report_id>/originals/<file>  -- full resolution, never served
                                            directly by a public route
  uploads/<report_id>/<file>            -- what /uploads actually serves;
                                            pixelated while the report is
                                            unclaimed, swapped for the
                                            original the moment a claim is
                                            verified (see matches.py's
                                            verify_claim -> reveal_photos)

Matching (CLIP embeddings) always reads from originals/, so redaction is
purely a *display* concern -- it never degrades match quality.
"""

import os
import shutil

from PIL import Image

# Bigger block = more pixelated / less recoverable detail. 18 keeps rough
# shape (item silhouette, background) visible while blurring out anything
# readable (text on a card, a face).
PIXEL_BLOCK_SIZE = 18


def originals_dir(report_dir: str) -> str:
    path = os.path.join(report_dir, "originals")
    os.makedirs(path, exist_ok=True)
    return path


def pixelate_image(src_path: str, dst_path: str, block_size: int = PIXEL_BLOCK_SIZE) -> None:
    """Downscale then upscale with nearest-neighbour to produce a blocky,
    unreadable version of the image -- cheap, dependency-free, and doesn't
    require a face/text detector to be "good enough" for this purpose."""
    with Image.open(src_path) as img:
        img = img.convert("RGB")
        w, h = img.size
        small_w = max(1, w // block_size)
        small_h = max(1, h // block_size)
        small = img.resize((small_w, small_h), resample=Image.BILINEAR)
        pixelated = small.resize((w, h), resample=Image.NEAREST)
        pixelated.save(dst_path)


def redact_photo(report_dir: str, filename: str) -> None:
    """Given a freshly-saved photo at report_dir/filename, moves the
    original into originals/ and writes a pixelated version back to the
    public path. Call this right after saving a high-risk report's photo."""
    public_path = os.path.join(report_dir, filename)
    original_path = os.path.join(originals_dir(report_dir), filename)

    shutil.copy2(public_path, original_path)
    pixelate_image(original_path, public_path)


def reveal_photos(report_dir: str, filenames: list[str]) -> None:
    """Copies each original back over its public path -- called once a
    claim is verified, since the redaction's job (hide it from public
    browsing) is done at that point."""
    src_dir = originals_dir(report_dir)
    for filename in filenames:
        src = os.path.join(src_dir, filename)
        dst = os.path.join(report_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)