import copy
import json
from pathlib import Path
from uuid import UUID

import pytest

from veritas.chain.leaves import DONATION_LEAF_TYPES, NO_TRIGGER, DonationLeaf, donation_tree
from veritas.chain.merkle import (
    MerkleError,
    StandardMerkleTree,
    leaf_hash,
    make_tree,
    process_proof,
    tree_proof,
)
from veritas.core.hashing import from_hex, keccak256, to_hex

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "merkle_vectors.json").read_text())

HOLDERS = [
    "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
    "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
]


def vector(name):
    return next(v for v in VECTORS if v["name"] == name)


def js_donation(i):
    """The same leaf as donation(i) in make_merkle_vectors.mjs."""
    return DonationLeaf(
        donation_id=UUID(int=0x1000 + i),
        holder=HOLDERS[i % 3],
        project_id=UUID(int=0xABC0 + i % 2),
        milestone=i % 4,
        amount=500 + 1250 * i,
        trigger=NO_TRIGGER if i % 3 == 0 else (0x7777 + i).to_bytes(32, "big"),
        salt=(0x5A170000 + i).to_bytes(32, "big"),
    )


@pytest.mark.parametrize("case", VECTORS, ids=lambda case: case["name"])
def test_same_tree_as_openzeppelin(case):
    loaded = StandardMerkleTree.load(case["dump"])
    rebuilt = StandardMerkleTree.of(loaded.values, loaded.types)
    assert to_hex(rebuilt.root) == case["root"]
    assert rebuilt.dump() == case["dump"]
    for i, (leaf, proof) in enumerate(zip(case["leaves"], case["proofs"], strict=True)):
        assert to_hex(rebuilt.leaf(i)) == leaf
        assert [to_hex(node) for node in rebuilt.proof(i)] == proof
        assert rebuilt.verify(i, rebuilt.proof(i))


def test_readme_root_from_the_oz_docs():
    assert vector("oz-readme")["root"] == (
        "0xd4dee0beab2d53f2cc83e567171bd2820e49898130a22622b10ead383e90bd77"
    )


@pytest.mark.parametrize("size", [1, 7, 16])
def test_donation_leaves_match_the_js_format(size):
    leaves = [js_donation(i) for i in range(size)]
    case = vector(f"donations-{size}")
    assert to_hex(donation_tree(leaves).root) == case["root"]
    assert [to_hex(leaf.hash()) for leaf in leaves] == case["leaves"]


def test_single_leaf_tree_is_its_own_root():
    tree = StandardMerkleTree.of([[HOLDERS[0], 5]], ["address", "uint256"])
    assert tree.root == tree.leaf(0)
    assert tree.proof(0) == []


def test_tampered_value_or_proof_fails():
    case = vector("donations-7")
    tree = StandardMerkleTree.load(case["dump"])
    proof = tree.proof(3)
    value = list(tree.values[3])
    assert StandardMerkleTree.verify_value(tree.root, tree.types, value, proof)
    value[4] += 1
    assert not StandardMerkleTree.verify_value(tree.root, tree.types, value, proof)
    assert not tree.verify(3, proof[:-1])
    assert not tree.verify(3, [keccak256(b"x")] + proof[1:])


def test_process_proof_matches_root():
    tree = StandardMerkleTree.load(vector("donations-16")["dump"])
    for i in range(16):
        assert process_proof(tree.leaf(i), tree.proof(i)) == tree.root


def test_load_rejects_broken_dumps():
    good = vector("donations-4")["dump"]

    wrong_format = copy.deepcopy(good)
    wrong_format["format"] = "simple-v1"
    bad_node = copy.deepcopy(good)
    bad_node["tree"][0] = to_hex(keccak256(b"not the root"))
    bad_index = copy.deepcopy(good)
    bad_index["values"][0]["treeIndex"] = 0
    bad_value = copy.deepcopy(good)
    bad_value["values"][1]["value"][4] = "1"
    missing_value = copy.deepcopy(good)
    missing_value["values"].pop()

    for dump in (wrong_format, bad_node, bad_index, bad_value, missing_value):
        with pytest.raises(MerkleError):
            StandardMerkleTree.load(dump)


def test_tree_building_edge_cases():
    with pytest.raises(MerkleError):
        make_tree([])
    with pytest.raises(MerkleError):
        make_tree([b"short"])
    tree = make_tree([keccak256(b"a"), keccak256(b"b"), keccak256(b"c")])
    with pytest.raises(MerkleError):
        tree_proof(tree, 0)
    with pytest.raises(MerkleError):
        leaf_hash(["address"], [HOLDERS[0], 1])


def test_donation_leaf_checks_its_fields():
    base = js_donation(1)
    assert base.holder == HOLDERS[1]
    assert (
        DonationLeaf(base.donation_id, HOLDERS[1].lower(), base.project_id, 0, 1).holder
        == (HOLDERS[1])
    )
    for bad in (
        {"holder": "0x1234"},
        {"milestone": 50},
        {"milestone": -1},
        {"amount": 0},
        {"amount": 2.5},
        {"salt": b"\x00" * 31},
    ):
        fields = {
            "donation_id": base.donation_id,
            "holder": base.holder,
            "project_id": base.project_id,
            "milestone": 1,
            "amount": 100,
        } | bad
        with pytest.raises(ValueError):
            DonationLeaf(**fields)


def test_fresh_leaves_get_random_salts():
    a = DonationLeaf(UUID(int=1), HOLDERS[0], UUID(int=2), 0, 100)
    b = DonationLeaf(UUID(int=1), HOLDERS[0], UUID(int=2), 0, 100)
    assert a.salt != b.salt
    assert a.hash() != b.hash()
    assert len(DONATION_LEAF_TYPES) == len(a.values())
    assert from_hex(to_hex(a.hash())) == a.hash()


def test_load_rejects_bytes_of_the_wrong_size():
    dump = copy.deepcopy(vector("donations-4")["dump"])
    dump["values"][0]["value"][6] = "0x" + "ab" * 31  # a bytes32 salt one byte short
    with pytest.raises(MerkleError):
        StandardMerkleTree.load(dump)
    dump["values"][0]["value"][6] = "0xzz"
    with pytest.raises(MerkleError):
        StandardMerkleTree.load(dump)


def test_donation_leaf_wants_real_types():
    base = js_donation(2)
    for bad in (
        {"donation_id": str(base.donation_id)},
        {"project_id": base.project_id.bytes},
        {"holder": None},
        {"milestone": True},
        {"milestone": "1"},
        {"trigger": "0x" + "00" * 32},
    ):
        fields = {
            "donation_id": base.donation_id,
            "holder": base.holder,
            "project_id": base.project_id,
            "milestone": 1,
            "amount": 100,
        } | bad
        with pytest.raises(ValueError):
            DonationLeaf(**fields)
