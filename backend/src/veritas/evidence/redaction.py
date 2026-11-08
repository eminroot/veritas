"""Redacting photos for the public copy: no metadata, faces and number plates blurred.

The public copy is built from the decoded pixels into a brand-new image, so nothing from the
original file survives: no EXIF (GPS position, time, phone model, serial numbers), no XMP, no
comments, no colour profile. Faces and number plates are found by a detector and blurred past
recognition: each region is first reduced to a few large blocks, then smoothed.

Which detector runs is pluggable. `HaarCascades` uses OpenCV's Haar cascades for frontal and
profile faces and for number plates. OpenCV 4 ships both the classifier and the cascade
files; OpenCV 5 dropped them from its wheels, so on OpenCV 5 `load_detector` finds nothing
unless a build with `CascadeClassifier` and a folder with the files are provided. Without a
detector that covers both faces and plates no photo is published: the public copy lists the
photos by count instead, because publishing a face cannot be undone.

The copy is a JPEG of at most 256 KiB, one IPFS block, so its CID is simply the SHA-256 of
the file and anyone can check a downloaded copy with plain tools. Larger photos are scaled
down until they fit; the full original stays in private storage for the officer.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image

from veritas.evidence.photos import open_photo

PUBLIC_MAX_BYTES = 256 * 1024
"""One IPFS block with Kubo's default chunker."""

PUBLIC_SIZES = (
    (2048, 85),
    (2048, 75),
    (1600, 75),
    (1600, 65),
    (1280, 65),
    (1280, 55),
    (1024, 55),
    (800, 50),
    (640, 45),
)
"""Longest side in pixels and JPEG quality, tried in order until the copy fits."""

NEEDED = frozenset({"faces", "plates"})
BLOCKS = 8
"""A blurred region keeps at most this many blocks across its longer side."""


class RedactionError(ValueError):
    """A photo that cannot be made safe to publish."""


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    width: int
    height: int
    label: str
    """"face" or "plate"."""


class Detector(Protocol):
    name: str
    covers: frozenset[str]
    """What it finds: "faces", "plates"."""

    def detect(self, image: np.ndarray) -> list[Box]:
        """Regions to blur in an RGB image (height x width x 3, uint8)."""
        ...


@dataclass(frozen=True)
class PublicPhoto:
    data: bytes
    width: int
    height: int
    blurred: tuple[Box, ...]


class HaarCascades:
    """OpenCV's Haar cascades for faces (frontal and both profiles) and number plates."""

    name = "opencv-haar"
    covers = NEEDED
    FILES = (
        ("face", "haarcascade_frontalface_default.xml", False),
        ("face", "haarcascade_profileface.xml", True),
        ("plate", "haarcascade_russian_plate_number.xml", False),
    )
    """Label, file, and whether to run it on the mirrored image too (profile faces look one
    way only)."""
    DETECT_SIDE = 2048
    """Detection runs on a copy scaled to this size, the public copy's largest: a face too small
    to look at here is no bigger than that in the copy."""

    def __init__(self, classifiers: Sequence[tuple[str, Any, bool]]) -> None:
        self._classifiers = list(classifiers)

    @classmethod
    def load(cls, folder: Path | None = None) -> HaarCascades | None:
        """The cascades, or None when this OpenCV build or the files are missing."""
        factory = getattr(cv2, "CascadeClassifier", None)
        if factory is None:
            return None
        if folder is None:
            bundled = getattr(getattr(cv2, "data", None), "haarcascades", None)
            if not bundled:
                return None
            folder = Path(bundled)
        classifiers = []
        for label, filename, mirror in cls.FILES:
            path = folder / filename
            if not path.is_file():
                return None
            classifier = factory(str(path))
            if classifier.empty():
                return None
            classifiers.append((label, classifier, mirror))
        return cls(classifiers)

    def detect(self, image: np.ndarray) -> list[Box]:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        height, width = gray.shape
        scale = min(1.0, self.DETECT_SIDE / max(height, width))
        if scale < 1.0:
            # Each side at least one pixel: a very thin photo would otherwise scale to nothing.
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            gray = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
        gray = cv2.equalizeHist(gray)
        found: list[Box] = []
        for label, classifier, mirror in self._classifiers:
            views = [(gray, False), (cv2.flip(gray, 1), True)] if mirror else [(gray, False)]
            for view, flipped in views:
                hits = classifier.detectMultiScale(
                    view, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20)
                )
                for x, y, w, h in hits:  # an empty tuple when nothing is found
                    if flipped:
                        x = view.shape[1] - x - w
                    found.append(
                        Box(
                            x=int(x / scale),
                            y=int(y / scale),
                            width=int(np.ceil(w / scale)),
                            height=int(np.ceil(h / scale)),
                            label=label,
                        )
                    )
        return found


def load_detector(folder: Path | None = None) -> Detector | None:
    """The best detector this server can run, or None."""
    return HaarCascades.load(folder)


def can_redact(detector: Detector | None) -> bool:
    return detector is not None and detector.covers >= NEEDED


def blur_boxes(image: np.ndarray, boxes: Sequence[Box], margin: float = 0.2) -> np.ndarray:
    """A copy of an RGB image with each box, and a margin around it, blurred past recognition."""
    out = image.copy()
    height, width = out.shape[:2]
    for box in boxes:
        pad_x, pad_y = int(box.width * margin), int(box.height * margin)
        x0, y0 = max(0, box.x - pad_x), max(0, box.y - pad_y)
        x1 = min(width, box.x + box.width + pad_x)
        y1 = min(height, box.y + box.height + pad_y)
        if x1 <= x0 or y1 <= y0:
            continue
        region = out[y0:y1, x0:x1]
        w, h = x1 - x0, y1 - y0
        longer = max(w, h)
        blocks = (max(1, w * BLOCKS // longer), max(1, h * BLOCKS // longer))
        small = cv2.resize(region, blocks, interpolation=cv2.INTER_AREA)
        coarse = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
        kernel = max(3, (min(w, h) // 4) | 1)
        out[y0:y1, x0:x1] = cv2.GaussianBlur(coarse, (kernel, kernel), 0)
    return out


def redact_photo(data: bytes, content_type: str, detector: Detector) -> PublicPhoto:
    """The public copy of a photo: upright, blurred where the detector finds people or plates,
    without any metadata, and small enough for one IPFS block."""
    try:
        pixels = np.asarray(open_photo(data, content_type, max_side=PUBLIC_SIZES[0][0]))
    except ValueError as exc:
        raise RedactionError(str(exc)) from exc
    try:
        boxes = tuple(detector.detect(pixels))
    except Exception as exc:  # a detector that cannot read the photo has not cleared it
        raise RedactionError(f"the detector failed on this photo: {exc}") from exc
    # A new image from bare pixels: nothing of the original file's metadata comes along.
    clean = Image.fromarray(blur_boxes(pixels, boxes) if boxes else pixels.copy())
    for side, quality in PUBLIC_SIZES:
        copy = clean.copy()
        copy.thumbnail((side, side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        copy.save(buffer, format="JPEG", quality=quality, optimize=True)
        if buffer.tell() <= PUBLIC_MAX_BYTES:
            return PublicPhoto(buffer.getvalue(), copy.width, copy.height, boxes)
    raise RedactionError("the photo does not fit in one public block even when scaled down")
