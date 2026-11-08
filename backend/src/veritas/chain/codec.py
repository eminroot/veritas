"""Contract call arguments and event data as JSON, and back.

The outbox stores each transaction's arguments, and the indexer stores each event, as JSON in
PostgreSQL, so both stay readable with plain SQL. The ABI says what every value is: bytes
travel as 0x hex, structs as JSON objects with their field names, integers as JSON numbers
(PostgreSQL keeps them exact), addresses checksummed. Decoding uses the same ABI to rebuild
the Python values web3 expects.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from eth_utils import event_abi_to_log_topic, to_checksum_address
from hexbytes import HexBytes
from web3 import Web3

from veritas.chain.contracts import abi


class CodecError(ValueError):
    """A value that does not fit the ABI it is meant for."""


def _is_array(kind: str) -> bool:
    return kind.endswith("]")


def _element(param: Mapping[str, Any]) -> dict[str, Any]:
    """The ABI entry for one element of an array parameter."""
    kind = param["type"]
    return {**param, "type": kind[: kind.rindex("[")]}


def to_json(value: Any, param: Mapping[str, Any]) -> Any:
    kind = param["type"]
    if _is_array(kind):
        return [to_json(item, _element(param)) for item in value]
    if kind == "tuple":
        components = param["components"]
        if isinstance(value, Mapping):
            return {c["name"]: to_json(value[c["name"]], c) for c in components}
        return {c["name"]: to_json(item, c) for c, item in zip(components, value, strict=True)}
    if kind.startswith("bytes"):
        return "0x" + bytes(HexBytes(value)).hex()
    if kind == "address":
        return to_checksum_address(value)
    if kind == "bool":
        return bool(value)
    if kind.startswith(("uint", "int")):
        return int(value)
    if kind == "string":
        return str(value)
    raise CodecError(f"type {kind} is not supported")


def from_json(value: Any, param: Mapping[str, Any]) -> Any:
    kind = param["type"]
    if _is_array(kind):
        if not isinstance(value, list):
            raise CodecError(f"{param.get('name', kind)} should be a list")
        return [from_json(item, _element(param)) for item in value]
    if kind == "tuple":
        components = param["components"]
        if not isinstance(value, Mapping):
            raise CodecError(f"{param.get('name', 'tuple')} should be an object")
        return tuple(from_json(value[c["name"]], c) for c in components)
    if kind.startswith("bytes"):
        if not isinstance(value, str) or not value.startswith("0x"):
            raise CodecError(f"{param.get('name', kind)} should be 0x hex")
        data = bytes.fromhex(value[2:])
        size = kind.removeprefix("bytes")
        if size and len(data) != int(size):
            raise CodecError(f"{param.get('name', kind)} needs {size} bytes, got {len(data)}")
        return data
    if kind == "address":
        return to_checksum_address(value)
    if kind == "bool":
        if not isinstance(value, bool):
            raise CodecError(f"{param.get('name', kind)} should be true or false")
        return value
    if kind.startswith(("uint", "int")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise CodecError(f"{param.get('name', kind)} should be an integer")
        return value
    if kind == "string":
        if not isinstance(value, str):
            raise CodecError(f"{param.get('name', kind)} should be a string")
        return value
    raise CodecError(f"type {kind} is not supported")


def function_abi(contract: str, function: str) -> dict[str, Any]:
    matches = [
        item
        for item in abi(contract)
        if item.get("type") == "function" and item.get("name") == function
    ]
    if len(matches) != 1:
        raise CodecError(f"{contract}.{function} is not one function in the ABI")
    return matches[0]


def encode_args(contract: str, function: str, args: Sequence[Any]) -> list[Any]:
    """Python call arguments to the JSON stored in the outbox."""
    inputs = function_abi(contract, function)["inputs"]
    if len(args) != len(inputs):
        raise CodecError(f"{contract}.{function} takes {len(inputs)} arguments, got {len(args)}")
    return [to_json(value, param) for value, param in zip(args, inputs, strict=True)]


def decode_args(contract: str, function: str, args: Sequence[Any]) -> list[Any]:
    """Outbox JSON back to the Python values web3 sends."""
    inputs = function_abi(contract, function)["inputs"]
    if len(args) != len(inputs):
        raise CodecError(f"{contract}.{function} takes {len(inputs)} arguments, got {len(args)}")
    return [from_json(value, param) for value, param in zip(args, inputs, strict=True)]


class EventDecoder:
    """Turns raw logs from Veritas contracts into (event name, JSON args).

    Decoding goes by the contract that emitted the log: vAZN's ERC-20 Transfer and the
    receipt's ERC-721 Transfer share a topic but not a layout.
    """

    def __init__(self, w3: Web3, contracts: Sequence[str]) -> None:
        self._contracts = {name: w3.eth.contract(abi=abi(name)) for name in contracts}
        self._events: dict[tuple[str, bytes], dict[str, Any]] = {}
        for name in contracts:
            for item in abi(name):
                if item.get("type") == "event" and not item.get("anonymous"):
                    self._events[(name, bytes(event_abi_to_log_topic(item)))] = item

    def decode(self, contract: str, log: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """None for a log the contract's ABI does not declare, like OpenZeppelin's Initialized."""
        topics = log.get("topics") or []
        if not topics:
            return None
        event_abi = self._events.get((contract, bytes(HexBytes(topics[0]))))
        if event_abi is None:
            return None
        name = event_abi["name"]
        data = self._contracts[contract].events[name]().process_log(log)
        args = {
            param["name"]: to_json(data["args"][param["name"]], param)
            for param in event_abi["inputs"]
        }
        return name, args
