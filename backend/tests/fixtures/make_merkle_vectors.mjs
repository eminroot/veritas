// Test vectors for backend/src/veritas/chain/merkle.py, made with the real
// OpenZeppelin library so the Python tree can be checked against it.
//
//   npm i @openzeppelin/merkle-tree@1.0.8
//   node make_merkle_vectors.mjs > merkle_vectors.json
//
// Everything below is fixed, so running it again gives the same file.

import { StandardMerkleTree } from "@openzeppelin/merkle-tree";

const hex = (n, bytes) => "0x" + BigInt(n).toString(16).padStart(bytes * 2, "0");

// Well known Anvil test accounts, used here as donor key addresses.
const holders = [
  "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
  "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
];

// Same field order and types as DONATION_LEAF_TYPES in veritas/chain/leaves.py.
const DONATION = ["bytes16", "address", "bytes16", "uint8", "uint64", "bytes32", "bytes32"];

const donation = (i) => [
  hex(0x1000 + i, 16),
  holders[i % holders.length],
  hex(0xabc0 + (i % 2), 16),
  String(i % 4),
  String(500 + 1250 * i),
  i % 3 === 0 ? hex(0, 32) : hex(0x7777 + i, 32),
  hex(0x5a170000 + i, 32),
];

const cases = [
  {
    name: "oz-readme",
    types: ["address", "uint256"],
    values: [
      ["0x1111111111111111111111111111111111111111", "5000000000000000000"],
      ["0x2222222222222222222222222222222222222222", "2500000000000000000"],
    ],
  },
  ...[1, 2, 3, 4, 7, 16].map((n) => ({
    name: `donations-${n}`,
    types: DONATION,
    values: Array.from({ length: n }, (_, i) => donation(i)),
  })),
];

const vectors = cases.map(({ name, types, values }) => {
  const tree = StandardMerkleTree.of(values, types);
  return {
    name,
    root: tree.root,
    leaves: values.map((value) => tree.leafHash(value)),
    proofs: values.map((_, i) => tree.getProof(i)),
    dump: tree.dump(),
  };
});

console.log(JSON.stringify(vectors, null, 2));
