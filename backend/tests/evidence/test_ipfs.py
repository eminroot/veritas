"""The Kubo RPC client, against a mock transport, and the in-memory fake."""

from __future__ import annotations

import json

import httpx
import pytest

from veritas.evidence.ipfs import CHUNK_SIZE, FakeIpfs, IpfsError, KuboClient, ipfs_for
from veritas.services.cid import raw_cid
from veritas.settings import Settings

DATA = b'{"format":"veritas.evidence.public/1"}'


def kubo(handler) -> KuboClient:
    return KuboClient("http://kubo.test:5001/", transport=httpx.MockTransport(handler))


def test_add_sends_the_file_with_explicit_options_and_returns_the_root_cid():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["body"] = request.read()
        seen["type"] = request.headers["content-type"]
        lines = [{"Name": "evidence.json", "Hash": raw_cid(DATA), "Size": str(len(DATA))}]
        return httpx.Response(200, text="\n".join(json.dumps(line) for line in lines) + "\n")

    assert kubo(handler).add(DATA, name="evidence.json") == raw_cid(DATA)
    assert seen["method"] == "POST"
    assert seen["path"] == "/api/v0/add"
    assert seen["params"] == {
        "cid-version": "1",
        "raw-leaves": "true",
        "hash": "sha2-256",
        "chunker": f"size-{CHUNK_SIZE}",
        "pin": "true",
        "quieter": "true",
    }
    assert seen["type"].startswith("multipart/form-data")
    assert DATA in seen["body"] and b'filename="evidence.json"' in seen["body"]


def test_a_node_that_stores_something_else_is_caught():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Name": "x", "Hash": raw_cid(b"other bytes")})

    with pytest.raises(IpfsError, match="should be " + raw_cid(DATA)):
        kubo(handler).add(DATA)


def test_kubo_errors_are_reported_in_its_own_words():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500, json={"Message": "blockstore: disk full", "Code": 0, "Type": "error"}
        )

    with pytest.raises(IpfsError, match="refused add: blockstore: disk full"):
        kubo(handler).add(DATA)


@pytest.mark.parametrize("body", ["", "not json", '{"Name": "x"}'])
def test_answers_without_a_cid_are_refused(body):
    with pytest.raises(IpfsError):
        kubo(lambda request: httpx.Response(200, text=body)).add(DATA)


def test_an_unreachable_node_is_an_ipfs_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(IpfsError, match="cannot reach the IPFS node at http://kubo.test:5001"):
        kubo(handler).add(DATA)


def test_cat_reads_a_file_back():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/api/v0/cat"
        assert request.url.params["arg"] == raw_cid(DATA)
        return httpx.Response(200, content=DATA)

    assert kubo(handler).cat(raw_cid(DATA)) == DATA


def test_files_larger_than_one_chunk_take_the_nodes_cid():
    big = bytes(CHUNK_SIZE + 1)
    tree = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Name": "big", "Hash": tree})

    assert kubo(handler).add(big) == tree


def test_the_fake_gives_kubos_cid_and_keeps_the_bytes():
    ipfs = FakeIpfs()
    cid = ipfs.add(DATA)
    assert cid == raw_cid(DATA) and cid.startswith("bafkrei")
    assert ipfs.cat(cid) == DATA
    with pytest.raises(IpfsError, match="nothing is stored"):
        ipfs.cat(raw_cid(b"never added"))
    with pytest.raises(IpfsError, match="up to"):
        ipfs.add(bytes(CHUNK_SIZE + 1))


def test_settings_choose_kubo_or_the_fake():
    assert isinstance(ipfs_for(Settings(_env_file=None, ipfs_fake=True)), FakeIpfs)
    client = ipfs_for(Settings(_env_file=None, ipfs_api_url="http://ipfs.internal:5001"))
    assert isinstance(client, KuboClient) and client.api_url == "http://ipfs.internal:5001"
