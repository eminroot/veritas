"""Opening uploaded photos safely, and their perceptual hashes.

A photo is decoded before anything else is done with it, so a file that only claims to be a
JPEG is refused at upload. The work a file can cause is bounded before any pixel is decoded:
the pixel count, a floor on picture-data bytes per pixel for large images (a big, nearly
empty image is a decompression bomb, not a photo; padding the file does not count), the
number of progressive JPEG scans (each one is another pass over every pixel), and the shape
(a camera photo is never a thin line). Both read the picture's own markers and chunks, so
data after it, like a phone's motion clip, changes nothing. A large JPEG can be decoded at a
reduced scale, which is all the hashes and the public copy need, and the API decodes only a
few uploads at a time; an upload that cannot get a decoder within seconds is told to come
back rather than left holding a worker thread.

Photos are turned upright first, from the EXIF orientation tag alone: the rest of the EXIF is
never rewritten, so a damaged tag elsewhere cannot make a portrait photo unusable. A JPEG
carrying a second picture (an MPF segment: HDR gain maps, depth or stereo cameras) is read as
its first picture.

pHash and dHash are 64-bit perceptual hashes from imagehash: two copies of one photo, even
resized or recompressed, differ in only a few bits, while different photos differ in about
half of them. They are stored as 8 bytes, most significant bit first, the same layout as
imagehash's hex form.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass

import imagehash
from PIL import Image

MAX_PIXELS = 60_000_000
"""More than any phone camera takes (a 50 megapixel sensor), less than a decompression bomb."""
LARGE_PIXELS = 4_000_000
MIN_BYTES_PER_MEGAPIXEL = 5_000
"""A camera photo of over 4 megapixels takes far more than this, even of a dark night."""
MAX_SCANS = 64
"""A camera's progressive JPEG has about ten scans, and a preview inside it as many again."""
MIN_SIDE = 100
MAX_ASPECT = 12
"""Wider than a phone's panorama."""
HASH_SIDE = 1024
"""Large JPEGs are decoded to about this size for the hashes, which use 32 x 32 pixels."""
MAX_PNG_PIXELS = 25_000_000
"""Phones write photos as JPEG; a PNG this large cannot be decoded at a smaller scale."""
MARKER = bytes([0xFF])

DECODING = threading.BoundedSemaphore(2)
"""How many uploaded photos one process decodes at once."""
DECODE_WAIT_SECONDS = 3.0
"""How long an upload waits for a free decoder before the API answers that it is busy. The
wait holds one of the API's worker threads, so it must stay short."""

FORMATS = {"image/jpeg": ("JPEG", "MPO"), "image/png": ("PNG",)}
TURNS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
"""EXIF orientation to the turn that makes the picture upright, as ImageOps.exif_transpose."""
ORIENTATION = 0x0112


class PhotoError(ValueError):
    """Bytes that are not a photo we can read."""


@dataclass(frozen=True)
class PerceptualHashes:
    phash: bytes
    dhash: bytes


def open_photo(data: bytes, content_type: str, *, max_side: int | None = None) -> Image.Image:
    """The photo, decoded, upright and in RGB. Raises PhotoError for anything else.

    With `max_side`, a large JPEG is decoded at a reduced scale, no smaller than that."""
    accepted = FORMATS.get(content_type)
    if accepted is None:
        raise PhotoError("a photo must be a JPEG or PNG image")
    try:
        # Opening reads only the header; nothing is decoded until every bound is checked.
        image = Image.open(io.BytesIO(data))
        if image.format not in accepted:
            raise PhotoError(f"the file is not a {accepted[0]} image, as its type says")
        _check_bounds(data, image)
        if max_side is not None and image.format in ("JPEG", "MPO"):
            image.draft("RGB", (max_side, max_side))
        image.load()
        return _upright(image).convert("RGB")
    except PhotoError:
        raise
    except Exception as exc:  # Pillow raises many kinds for a damaged or hostile file
        raise PhotoError("the photo cannot be read; it may be damaged or incomplete") from exc


def _check_bounds(data: bytes, image: Image.Image) -> None:
    width, height = image.size
    pixels = width * height
    limit = MAX_PIXELS if image.format != "PNG" else MAX_PNG_PIXELS
    if pixels > limit:
        raise PhotoError(
            f"the photo has {width} x {height} pixels; at most {limit // 1_000_000} megapixels "
            f"are accepted{' in a PNG' if image.format == 'PNG' else ''}"
        )
    if min(width, height) < MIN_SIDE or max(width, height) > MAX_ASPECT * min(width, height):
        raise PhotoError(f"the photo is {width} x {height} pixels, which no camera photo is")
    if image.format == "PNG":
        coded = _png_coded(data)
    else:
        scans, coded = _jpeg_scans(data)
        if scans > MAX_SCANS:
            raise PhotoError(f"the JPEG has more than {MAX_SCANS} scans, which no camera writes")
    if pixels > LARGE_PIXELS and coded * 1_000_000 < pixels * MIN_BYTES_PER_MEGAPIXEL:
        raise PhotoError(
            f"the photo has {width} x {height} pixels in only {coded} bytes of picture data, "
            "which no camera photo does"
        )


def _jpeg_scans(data: bytes) -> tuple[int, int]:
    """The scans of the first picture and the bytes of their coded data, read from its markers
    up to its end marker: what the decoder works through, whatever follows the picture (a
    phone's motion clip, a second picture) or sits in its metadata."""
    scans = coded = 0
    i, end = 2, len(data)
    while i + 4 <= end:
        if data[i] != 0xFF:
            # Not a marker where one should be. libjpeg skips such bytes and reads on, so
            # scans could hide behind them: count every scan marker left in the file instead,
            # which can only count too many.
            scans += data.count(b"\xff\xda", i)
            break
        marker = data[i + 1]
        if marker == 0xFF:  # a fill byte before a marker
            i += 1
            continue
        if marker == 0xD9:  # the end of the picture
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # markers without a length
            i += 2
            continue
        i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
        if marker != 0xDA:
            continue
        scans += 1
        if scans > MAX_SCANS:
            break
        start = i
        while True:  # the coded data runs to the next marker that is not stuffing or a restart
            i = data.find(MARKER, i)
            if i < 0 or i + 1 >= end:
                i = end
                break
            if data[i + 1] == 0x00 or 0xD0 <= data[i + 1] <= 0xD7:
                i += 2
                continue
            break
        coded += i - start
    return scans, coded


def _png_coded(data: bytes) -> int:
    """The bytes of a PNG's image data (its IDAT chunks), not of what else it carries."""
    coded, i = 0, 8
    while i + 8 <= len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        if kind == b"IDAT":
            coded += length
        elif kind == b"IEND":
            break
        i += 12 + length
    return coded


def _upright(image: Image.Image) -> Image.Image:
    """The picture turned upright by its EXIF orientation. Unreadable EXIF leaves it as is."""
    try:
        orientation = int(image.getexif().get(ORIENTATION, 1))
    except Exception:
        return image
    turn = TURNS.get(orientation)
    return image.transpose(turn) if turn is not None else image


def perceptual_hashes(image: Image.Image) -> PerceptualHashes:
    return PerceptualHashes(
        phash=bytes.fromhex(str(imagehash.phash(image))),
        dhash=bytes.fromhex(str(imagehash.dhash(image))),
    )


def hamming(a: bytes, b: bytes) -> int:
    """How many bits differ between two hashes of the same length."""
    if len(a) != len(b):
        raise ValueError("hashes of different lengths cannot be compared")
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).bit_count()
