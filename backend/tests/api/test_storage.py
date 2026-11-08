import uuid

import pytest

from veritas.core.hashing import sha256
from veritas.storage import LocalStorage, StorageError, kyb_key


def test_put_get_exists_delete(tmp_path):
    storage = LocalStorage(tmp_path)
    key = kyb_key(uuid.UUID(int=7), sha256(b"charter"))
    assert key == f"kyb/{uuid.UUID(int=7)}/{sha256(b'charter').hex()}"
    assert not storage.exists(key)
    storage.put(key, b"charter")
    assert storage.exists(key)
    assert storage.get(key) == b"charter"
    storage.put(key, b"charter")  # storing the same content again is harmless
    files = [path.name for path in tmp_path.rglob("*") if path.is_file()]
    assert files == [sha256(b"charter").hex()]
    storage.delete(key)
    storage.delete(key)
    assert not storage.exists(key)
    with pytest.raises(KeyError):
        storage.get(key)


@pytest.mark.parametrize(
    "key", ["", "../secret", "kyb/../../etc", "/abs", "a//b", "a\\b", ".hidden", "C:/x", "a/"]
)
def test_keys_cannot_leave_the_root(tmp_path, key):
    storage = LocalStorage(tmp_path)
    with pytest.raises(StorageError):
        storage.put(key, b"x")
    with pytest.raises(StorageError):
        storage.get(key)
