"""Merkle trees in the exact format of OpenZeppelin's StandardMerkleTree.

Leaves are keccak256(keccak256(abi.encode(types, values))), inner nodes hash their
two children in sorted order, and leaves are sorted by hash before the tree is
built. That is what @openzeppelin/merkle-tree produces and what OpenZeppelin's
MerkleProof.verify checks on-chain, so roots, proofs and dumps move between this
module, the JS verifier page and the contracts unchanged.

The tree is stored as a flat array the way the JS library stores it: the root at
index 0, the children of node i at 2i+1 and 2i+2, and the leaves at the end in
reverse order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from eth_abi import encode
from eth_utils import to_checksum_address

from veritas.core.hashing import from_hex, keccak256, to_hex

DUMP_FORMAT = "standard-v1"


class MerkleError(ValueError):
    """A tree, proof or dump that does not hold together."""


def leaf_hash(types: Sequence[str], value: Sequence[Any]) -> bytes:
    """The leaf for one value: keccak256(keccak256(abi.encode(types, value)))."""
    if len(types) != len(value):
        raise MerkleError(f"{len(value)} fields for {len(types)} types")
    return keccak256(keccak256(encode(list(types), list(value))))


def hash_pair(a: bytes, b: bytes) -> bytes:
    """Hash two nodes in sorted order, like OpenZeppelin's commutativeKeccak256."""
    return keccak256(a + b if a <= b else b + a)


def process_proof(leaf: bytes, proof: Sequence[bytes]) -> bytes:
    """Walk a proof up from a leaf and return the root it leads to."""
    node = leaf
    for sibling in proof:
        node = hash_pair(node, sibling)
    return node


def make_tree(leaves: Sequence[bytes]) -> list[bytes]:
    """Build the flat tree array from leaves that are already hashed and ordered."""
    if not leaves:
        raise MerkleError("a Merkle tree needs at least one leaf")
    for leaf in leaves:
        if len(leaf) != 32:
            raise MerkleError("leaves must be 32 bytes")
    size = 2 * len(leaves) - 1
    tree = [b""] * size
    for position, leaf in enumerate(leaves):
        tree[size - 1 - position] = leaf
    for index in range(size - 1 - len(leaves), -1, -1):
        tree[index] = hash_pair(tree[2 * index + 1], tree[2 * index + 2])
    return tree


def tree_proof(tree: Sequence[bytes], index: int) -> list[bytes]:
    """Sibling hashes from the leaf at tree position `index` up to the root."""
    if not len(tree) // 2 <= index < len(tree):
        raise MerkleError(f"position {index} is not a leaf")
    proof = []
    while index > 0:
        sibling = index + 1 if index % 2 == 1 else index - 1
        proof.append(tree[sibling])
        index = (index - 1) // 2
    return proof


def _check_tree(tree: Sequence[bytes]) -> None:
    if len(tree) % 2 == 0:
        raise MerkleError("a tree array always has an odd length")
    for index in range(len(tree) // 2):
        if tree[index] != hash_pair(tree[2 * index + 1], tree[2 * index + 2]):
            raise MerkleError(f"node {index} does not match its children")


def _value_to_json(abi_type: str, value: Any) -> Any:
    if abi_type == "address":
        return to_checksum_address(value)
    if abi_type == "bool":
        return bool(value)
    if abi_type == "string":
        return str(value)
    if abi_type.startswith(("uint", "int")):
        return str(int(value))
    if abi_type.startswith("bytes"):
        return "0x" + bytes(value).hex()
    raise MerkleError(f"type {abi_type} is not supported in dumps")


def _value_from_json(abi_type: str, value: Any) -> Any:
    if abi_type == "address":
        return to_checksum_address(value)
    if abi_type == "bool":
        if not isinstance(value, bool):
            raise MerkleError(f"expected a bool, got {value!r}")
        return value
    if abi_type == "string":
        return str(value)
    if abi_type.startswith(("uint", "int")):
        return int(value)
    if abi_type.startswith("bytes"):
        if not isinstance(value, str) or not value.startswith("0x"):
            raise MerkleError(f"expected 0x hex for {abi_type}, got {value!r}")
        try:
            data = bytes.fromhex(value[2:])
        except ValueError as exc:
            raise MerkleError(f"not hex: {value!r}") from exc
        size = abi_type.removeprefix("bytes")
        if size and len(data) != int(size):
            # eth_abi would quietly pad a short value, giving a different leaf.
            raise MerkleError(f"{abi_type} needs {size} bytes, got {len(data)}")
        return data
    raise MerkleError(f"type {abi_type} is not supported in dumps")


@dataclass(frozen=True)
class StandardMerkleTree:
    """A tree over ABI-encoded values, built and dumped like the OpenZeppelin JS one."""

    types: tuple[str, ...]
    tree: tuple[bytes, ...]
    values: tuple[tuple[Any, ...], ...]
    tree_indices: tuple[int, ...]

    @classmethod
    def of(
        cls,
        values: Sequence[Sequence[Any]],
        types: Sequence[str],
        *,
        sort_leaves: bool = True,
    ) -> StandardMerkleTree:
        hashed = [(leaf_hash(types, value), index) for index, value in enumerate(values)]
        if sort_leaves:
            hashed.sort(key=lambda item: item[0])  # stable, like Array.prototype.sort
        tree = make_tree([leaf for leaf, _ in hashed])
        indices = [0] * len(values)
        for position, (_, value_index) in enumerate(hashed):
            indices[value_index] = len(tree) - 1 - position
        return cls(tuple(types), tuple(tree), tuple(tuple(v) for v in values), tuple(indices))

    @property
    def root(self) -> bytes:
        return self.tree[0]

    def leaf(self, value_index: int) -> bytes:
        return self.tree[self.tree_indices[value_index]]

    def proof(self, value_index: int) -> list[bytes]:
        return tree_proof(self.tree, self.tree_indices[value_index])

    def verify(self, value_index: int, proof: Sequence[bytes]) -> bool:
        return process_proof(self.leaf(value_index), proof) == self.root

    @staticmethod
    def verify_value(
        root: bytes, types: Sequence[str], value: Sequence[Any], proof: Sequence[bytes]
    ) -> bool:
        """Check a value against a root without the tree, the way a contract does."""
        return process_proof(leaf_hash(types, value), proof) == root

    def dump(self) -> dict[str, Any]:
        """The same JSON shape that StandardMerkleTree.dump() gives in JS."""
        return {
            "format": DUMP_FORMAT,
            "leafEncoding": list(self.types),
            "tree": [to_hex(node) for node in self.tree],
            "values": [
                {
                    "value": [_value_to_json(t, v) for t, v in zip(self.types, value, strict=True)],
                    "treeIndex": index,
                }
                for value, index in zip(self.values, self.tree_indices, strict=True)
            ],
        }

    @classmethod
    def load(cls, data: Mapping[str, Any]) -> StandardMerkleTree:
        """Read a dump and check that every node and every value fits the tree."""
        if data.get("format") != DUMP_FORMAT:
            raise MerkleError(f"unknown dump format: {data.get('format')!r}")
        types = tuple(data["leafEncoding"])
        tree = tuple(from_hex(node) for node in data["tree"])
        _check_tree(tree)
        values, indices = [], []
        for entry in data["values"]:
            value = tuple(
                _value_from_json(t, v) for t, v in zip(types, entry["value"], strict=True)
            )
            index = entry["treeIndex"]
            if not len(tree) // 2 <= index < len(tree) or tree[index] != leaf_hash(types, value):
                raise MerkleError(f"value does not match the leaf at position {index}")
            values.append(value)
            indices.append(index)
        if len(set(indices)) != len(indices) or len(indices) != (len(tree) + 1) // 2:
            raise MerkleError("every leaf must belong to exactly one value")
        return cls(types, tree, tuple(values), tuple(indices))
