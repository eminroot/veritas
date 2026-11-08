import pytest

from veritas.services.cid import raw_cid


@pytest.mark.parametrize(
    ("data", "cid"),
    [
        # Well-known CIDs: `ipfs add --cid-version 1 --raw-leaves` of an empty file and of
        # "hello world" without a newline.
        (b"", "bafkreihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku"),
        (b"hello world", "bafkreifzjut3te2nhyekklss27nh3k72ysco7y32koao5eei66wof36n5e"),
    ],
)
def test_raw_cid_matches_ipfs(data, cid):
    assert raw_cid(data) == cid
