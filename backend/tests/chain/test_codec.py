import json
from pathlib import Path

import pytest

from veritas.chain import eip712
from veritas.chain.codec import CodecError, EventDecoder, decode_args, encode_args
from veritas.chain.contracts import SYSTEM, Contracts, deploy_system, send
from veritas.chain.project import ProjectConfig, launch_message
from veritas.passport import Passport

EXAMPLE = Path(__file__).parents[3] / "docs" / "examples" / "passport.example.json"
CHARITY = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"


@pytest.fixture
def passport():
    return Passport.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))


def test_create_project_args_survive_json(passport):
    config = ProjectConfig.from_passport(passport, CHARITY)
    args = [config.abi_value(), passport.digest(), "bafy", b"\x01" * 65]
    stored = json.loads(json.dumps(encode_args("EscrowFactory", "createProject", args)))
    assert stored[0]["projectId"] == "0x" + passport.project_id.hex
    assert stored[0]["rules"]["voteWindow"] == 72 * 3600
    assert stored[1] == "0x" + passport.digest().hex()
    decoded = decode_args("EscrowFactory", "createProject", stored)
    assert decoded[0] == tuple(
        tuple(part) if isinstance(part, tuple) else part for part in config.abi_value()
    )
    assert decoded[1:] == args[1:]


@pytest.mark.parametrize(
    ("index", "value"),
    [(1, "0x" + "ab" * 31), (1, "not hex"), (2, 5), (3, ["0x01"])],
)
def test_bad_values_are_refused(passport, index, value):
    config = ProjectConfig.from_passport(passport, CHARITY)
    stored = encode_args(
        "EscrowFactory", "createProject", [config.abi_value(), passport.digest(), "x", b"\x00"]
    )
    stored[index] = value
    with pytest.raises((CodecError, ValueError)):
        decode_args("EscrowFactory", "createProject", stored)


def test_argument_count_is_checked():
    with pytest.raises(CodecError):
        encode_args("EscrowFactory", "createProject", [1, 2])
    with pytest.raises(CodecError):
        encode_args("EscrowFactory", "noSuchFunction", [])


def test_events_from_anvil_decode_to_json(w3, accounts, passport):
    deployment = deploy_system(
        w3,
        accounts["deployer"],
        admin=accounts["deployer"].address,
        relayer=accounts["relayer"].address,
        bank=accounts["bank"].address,
    )
    chain = Contracts(w3, deployment)
    admin = accounts["deployer"]
    for call in (
        chain.hub.functions.setCharity(accounts["charity"].address, True),
        chain.hub.functions.setOfficer(accounts["officer"].address, True),
    ):
        send(w3, admin, call.build_transaction({"from": admin.address}))
    config = ProjectConfig.from_passport(passport, accounts["charity"].address)
    message = launch_message(passport, config, passport.digest(), "bafy")
    domain = eip712.Domain(w3.eth.chain_id, deployment.hub)
    signature = eip712.sign(accounts["charity"].key, domain, "ProjectLaunch", message)
    call = chain.factory.functions.createProject(
        config.abi_value(), passport.digest(), "bafy", signature
    )
    relayer = accounts["relayer"]
    receipt = send(w3, relayer, call.build_transaction({"from": relayer.address}))

    names = {address: name for name, address in deployment.addresses.items()}
    decoder = EventDecoder(w3, [*SYSTEM])
    seen = {}
    for log in receipt["logs"]:
        contract = names.get(log["address"], "MilestoneEscrow")
        decoded = decoder.decode(contract, log)
        if decoded:
            seen[decoded[0]] = decoded[1]
    assert seen["ProjectCreated"]["projectId"] == "0x" + passport.project_id.hex
    assert seen["ProjectCreated"]["passportHash"] == "0x" + passport.digest().hex()
    assert seen["PassportRecorded"]["version"] == 1
    assert seen["EscrowRegistered"]["escrow"] == seen["ProjectCreated"]["escrow"]
