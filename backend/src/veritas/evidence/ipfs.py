"""Publishing public copies to IPFS through Kubo, and an in-process fake for tests and laptops.

`KuboClient` talks to Kubo's RPC API (port 5001 by default, never exposed publicly), not to a
gateway. Every file is added with CIDv1, raw leaves, SHA-256 and the default 256 KiB chunker,
all passed explicitly so a node's own settings cannot change the result, and pinned. A file
that fits in one chunk then has the CID `veritas.services.cid.raw_cid` computes without a
node, so the client checks Kubo's answer against it: a node that stores something else is
caught at once. Everything Veritas publishes fits in one chunk on purpose.

`FakeIpfs` keeps files in memory and gives the CID Kubo would. It stands in for Kubo in tests
and, with VERITAS_IPFS_FAKE, on a laptop without a node; production refuses it.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx

from veritas.services.cid import raw_cid
from veritas.settings import Settings

CHUNK_SIZE = 256 * 1024
ADD_PARAMS = {
    "cid-version": "1",
    "raw-leaves": "true",
    "hash": "sha2-256",
    "chunker": f"size-{CHUNK_SIZE}",
    "pin": "true",
    "quieter": "true",
}


class IpfsError(RuntimeError):
    """The IPFS node refused, could not be reached, or answered something unexpected."""


class Ipfs(Protocol):
    def add(self, data: bytes, *, name: str = "file") -> str:
        """Add and pin the bytes. Returns their CID."""
        ...

    def cat(self, cid: str) -> bytes: ...


class KuboClient:
    def __init__(
        self,
        api_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.api_url}/api/v0/", timeout=timeout, transport=transport
        )

    def add(self, data: bytes, *, name: str = "file") -> str:
        response = self._post(
            "add", params=ADD_PARAMS, files={"file": (name, data, "application/octet-stream")}
        )
        cid = _added_cid(response.text)
        if len(data) <= CHUNK_SIZE and cid != raw_cid(data):
            raise IpfsError(
                f"Kubo answered CID {cid} for {len(data)} bytes that should be {raw_cid(data)}"
            )
        return cid

    def cat(self, cid: str) -> bytes:
        return self._post("cat", params={"arg": cid}).content

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        # Kubo's RPC API takes POST for everything, so a browser cannot be tricked into it.
        try:
            response = self._client.post(path, **kwargs)
        except httpx.HTTPError as exc:
            raise IpfsError(f"cannot reach the IPFS node at {self.api_url}: {exc}") from exc
        if response.status_code != 200:
            raise IpfsError(f"the IPFS node refused {path}: {_message(response)}")
        return response


def _added_cid(body: str) -> str:
    """The root CID from `add`'s output: one JSON object per line, the root last."""
    cid = None
    for line in body.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            raise IpfsError(
                f"the IPFS node gave an answer that is not JSON: {line[:200]}"
            ) from None
        if isinstance(entry, dict) and isinstance(entry.get("Hash"), str):
            cid = entry["Hash"]
    if not cid:
        raise IpfsError("the IPFS node did not say which CID it stored")
    return cid


def _message(response: httpx.Response) -> str:
    """Kubo's error text: {"Message": "...", "Code": 0, "Type": "error"}."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("Message"):
        return str(body["Message"])
    return f"HTTP {response.status_code} {response.text[:200]}".strip()


class FakeIpfs:
    """Files in a dict. Only files of one chunk, whose CID it can give exactly as Kubo would."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def add(self, data: bytes, *, name: str = "file") -> str:
        if len(data) > CHUNK_SIZE:
            raise IpfsError(f"the fake IPFS holds files of up to {CHUNK_SIZE} bytes only")
        cid = raw_cid(data)
        self.files[cid] = data
        return cid

    def cat(self, cid: str) -> bytes:
        try:
            return self.files[cid]
        except KeyError:
            raise IpfsError(f"nothing is stored under {cid}") from None


def ipfs_for(settings: Settings) -> Ipfs:
    if settings.ipfs_fake:
        return FakeIpfs()
    return KuboClient(settings.ipfs_api_url, timeout=settings.ipfs_timeout_seconds)
