"""Private file storage for originals: KYB documents now, evidence later.

Nothing here is public. Files are addressed by key, and keys are content-addressed
where that makes sense (`kyb/<owner_id>/<sha256 hex>`), so storing the same file
twice is harmless and a stored file can be checked against its name. LocalStorage
is for development and tests; an S3-compatible bucket comes later behind the
same interface.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import UUID

_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


class StorageError(ValueError):
    """A key that is not allowed."""


class PrivateStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes:
        """The stored bytes. Raises KeyError if nothing is stored under `key`."""
        ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None:
        """Remove the object. Removing a key that is not there is not an error."""
        ...


def check_key(key: str) -> list[str]:
    """Split a key into its segments, refusing anything that could leave the storage root."""
    segments = key.split("/")
    if not key or not all(_SEGMENT.fullmatch(segment) for segment in segments):
        raise StorageError(f"not a storage key: {key!r}")
    return segments


def kyb_key(owner_id: UUID, sha256: bytes) -> str:
    return f"kyb/{owner_id}/{sha256.hex()}"


class LocalStorage:
    """Files in a directory tree. Writes go to a temporary file first, so a reader
    never sees half a file."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root.joinpath(*check_key(key))

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
