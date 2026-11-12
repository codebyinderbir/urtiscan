"""Image storage and ingestion.

``LocalStorage`` writes under ``data/photos``. A pilot deployment would swap in an
S3-compatible implementation with the same three methods (server-side encryption, Canadian
region).

Ingestion fixes orientation from EXIF, keeps only the camera model and capture time, and
re-encodes the image so GPS and all other metadata are dropped before anything is stored.
"""
from __future__ import annotations

import io
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageOps

from .config import settings

_EXIF_MODEL = 0x0110
_EXIF_MAKE = 0x010F
_EXIF_DATETIME_ORIGINAL = 0x9003
_EXIF_IFD = 0x8769


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put_image(self, key: str, image_bgr: np.ndarray, quality: int = 95) -> str:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        params = [cv2.IMWRITE_JPEG_QUALITY, quality] if key.endswith(".jpg") else []
        if not cv2.imwrite(str(p), image_bgr, params):
            raise IOError(f"could not write {key}")
        return key

    def get_image(self, key: str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray:
        img = cv2.imread(str(self.path(key)), flags)
        if img is None:
            raise FileNotFoundError(key)
        return img

    def delete_prefix(self, prefix: str) -> None:
        p = self.path(prefix)
        if p.is_dir():
            shutil.rmtree(p)


storage = LocalStorage(settings.photos_dir)


@dataclass
class IngestedImage:
    original_bgr: np.ndarray
    working_bgr: np.ndarray
    device_model: Optional[str]
    exif_taken_at: Optional[datetime]


def ingest(data: bytes, working_long_edge: int) -> IngestedImage:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("File is not a readable image (JPEG, PNG, HEIC not yet supported).") from exc

    exif = img.getexif()
    make = str(exif.get(_EXIF_MAKE, "")).strip()
    model = str(exif.get(_EXIF_MODEL, "")).strip()
    device = " ".join(x for x in (make, model) if x) or None
    taken = None
    raw_dt = exif.get_ifd(_EXIF_IFD).get(_EXIF_DATETIME_ORIGINAL) if exif else None
    if raw_dt:
        try:
            taken = datetime.strptime(str(raw_dt), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            taken = None

    img = ImageOps.exif_transpose(img).convert("RGB")  # pixels only from here on
    original = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    h, w = original.shape[:2]
    scale = working_long_edge / max(h, w)
    working = (
        cv2.resize(original, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        if scale < 1
        else original.copy()
    )
    return IngestedImage(original, working, device, taken)


__all__ = ["storage", "ingest", "IngestedImage", "LocalStorage"]
