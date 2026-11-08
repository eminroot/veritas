"""Redaction: nothing of the original file's metadata survives, and what is found is blurred."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from PIL import Image

from veritas.evidence.redaction import (
    PUBLIC_MAX_BYTES,
    Box,
    HaarCascades,
    RedactionError,
    blur_boxes,
    can_redact,
    load_detector,
    redact_photo,
)

from .kit import FixedBoxes, jpeg, scene, with_gps


def checkerboard(size: int = 400, square: int = 4) -> np.ndarray:
    tiles = (np.indices((size, size)) // square).sum(axis=0) % 2
    return np.repeat((tiles * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def test_exif_gps_and_the_camera_model_are_gone():
    original = with_gps(scene(1), 40.7905, 48.151)
    gps = Image.open(io.BytesIO(original)).getexif().get_ifd(0x8825)
    assert gps[1] == "N" and gps[2][0] == 40.0  # the phone wrote where it was

    public = redact_photo(original, "image/jpeg", FixedBoxes())
    copy = Image.open(io.BytesIO(public.data))
    assert copy.format == "JPEG"
    assert not copy.getexif()
    assert not {"exif", "icc_profile", "comment", "xmp"} & set(copy.info)
    assert b"Exif" not in public.data and b"Veritas Test Phone" not in public.data
    assert (public.width, public.height) == (960, 720)
    assert len(public.data) <= PUBLIC_MAX_BYTES


def test_blur_covers_the_boxes_and_leaves_the_rest_alone():
    image = checkerboard()
    out = blur_boxes(image, [Box(100, 100, 100, 100, "face")], margin=0)
    assert image[100:200, 100:200].std() > 120
    assert out[100:200, 100:200].std() < 10  # nothing left of the pattern
    untouched = np.ones(image.shape[:2], dtype=bool)
    untouched[100:200, 100:200] = False
    assert np.array_equal(out[untouched], image[untouched])


def test_blur_takes_a_margin_and_stays_inside_the_image():
    image = checkerboard()
    out = blur_boxes(image, [Box(380, -20, 100, 60, "plate")])
    assert out[0:30, 380:400].std() < 40
    assert out.shape == image.shape


def test_the_copy_is_upright_whatever_the_orientation_tag():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to view
    data = jpeg(scene(2, (300, 200)), exif=exif)
    public = redact_photo(data, "image/jpeg", FixedBoxes())
    assert (public.width, public.height) == (200, 300)


def test_a_large_detailed_photo_is_scaled_until_it_fits_one_block():
    noise = np.random.default_rng(1).integers(0, 256, (2000, 3000, 3), dtype=np.uint8)
    data = jpeg(Image.fromarray(noise), quality=95)
    assert len(data) > 3 * PUBLIC_MAX_BYTES
    public = redact_photo(data, "image/jpeg", FixedBoxes())
    assert len(public.data) <= PUBLIC_MAX_BYTES
    assert max(public.width, public.height) < 3000
    assert public.width / public.height == pytest.approx(1.5, rel=0.01)


def test_detected_regions_are_counted_and_blurred():
    data = jpeg(Image.fromarray(checkerboard(600)))
    face = Box(200, 200, 120, 120, "face")
    public = redact_photo(data, "image/jpeg", FixedBoxes((face,)))
    assert public.blurred == (face,)
    copy = np.asarray(Image.open(io.BytesIO(public.data)))
    assert copy[210:310, 210:310].std() < 20 and copy[400:500, 400:500].std() > 100


def test_files_that_are_not_photos_cannot_be_redacted():
    with pytest.raises(RedactionError):
        redact_photo(b"\xff\xd8\xff" + bytes(50), "image/jpeg", FixedBoxes())


def test_redaction_needs_a_detector_for_faces_and_plates():
    assert can_redact(FixedBoxes())
    assert not can_redact(FixedBoxes(covers=frozenset({"faces"})))
    assert not can_redact(None)


class FakeCascade:
    """Answers like cv2.CascadeClassifier.detectMultiScale: an array of x, y, w, h rows."""

    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def detectMultiScale(self, image, **options):  # noqa: N802  (OpenCV's name)
        self.calls.append(image.shape)
        return np.array(self.hits) if self.hits else ()


def test_haar_detections_are_scaled_back_and_mirrored_ones_flipped():
    faces = FakeCascade([(10, 20, 30, 40)])
    plates = FakeCascade([])
    detector = HaarCascades([("face", faces, True), ("plate", plates, False)])
    image = np.zeros((2048, 4096, 3), dtype=np.uint8)  # detection runs at half size

    boxes = detector.detect(image)
    assert faces.calls == [(1024, 2048), (1024, 2048)] and plates.calls == [(1024, 2048)]
    assert boxes == [
        Box(x=20, y=40, width=60, height=80, label="face"),
        Box(x=4096 - 20 - 60, y=40, width=60, height=80, label="face"),
    ]


def test_haar_cascades_are_used_only_when_opencv_provides_them(monkeypatch, tmp_path):
    monkeypatch.delattr(cv2, "CascadeClassifier", raising=False)
    assert HaarCascades.load() is None

    class Loaded:
        def __init__(self, path):
            self.path = path

        def empty(self):
            return False

    monkeypatch.setattr(cv2, "CascadeClassifier", Loaded, raising=False)
    assert HaarCascades.load(tmp_path) is None  # the files are not there
    for _, filename, _ in HaarCascades.FILES:
        (tmp_path / filename).write_text("<opencv_storage/>")
    assert isinstance(HaarCascades.load(tmp_path), HaarCascades)


def test_the_detector_this_server_has_runs_on_a_plain_image():
    detector = load_detector()
    if detector is None:
        pytest.skip("this OpenCV build has no Haar cascades (OpenCV 5 dropped them)")
    plain = np.full((480, 640, 3), 128, dtype=np.uint8)
    assert detector.detect(plain) == []


def test_a_very_thin_photo_does_not_crash_the_detector():
    """OpenCV's resize refuses a size of zero; a 5000 x 1 picture scaled to the detection size
    used to ask for one."""
    cascades = HaarCascades([])  # no classifiers: only the scaling runs
    assert cascades.detect(np.zeros((1, 5000, 3), dtype=np.uint8)) == []
    assert cascades.detect(np.zeros((6000, 2, 3), dtype=np.uint8)) == []
