from pathlib import Path

from veritas.chain import eip712
from veritas.chain.contracts import SYSTEM, Contracts, Deployment, abi, deploy_system, send
from veritas.chain.project import ProjectConfig, launch_message
from veritas.passport import Passport

EXAMPLE = Path(__file__).parents[3] / "docs" / "examples" / "passport.example.json"


def test_every_artifact_has_abi_and_bytecode():
    for name in SYSTEM:
        assert any(item.get("type") == "constructor" for item in abi(name))
    assert any(item.get("name") == "createProject" for item in abi("EscrowFactory"))


def test_deployment_json_round_trip():
    data = {"chainId": 31337, "startBlock": 7} | {name: "0x" + "11" * 20 for name in SYSTEM}
    deployment = Deployment.from_json(data)
    assert Deployment.from_json(deployment.to_json()) == deployment
    assert deployment.hub == "0x1111111111111111111111111111111111111111"


def test_deploy_and_launch_the_example_passport(w3, accounts):
    deployment = deploy_system(
        w3,
        accounts["deployer"],
        admin=accounts["deployer"].address,
        relayer=accounts["relayer"].address,
        bank=accounts["bank"].address,
    )
    chain = Contracts(w3, deployment)
    assert chain.hub.functions.wired().call()
    assert chain.hub.functions.ledger().call() == deployment.addresses["DonationLedger"]

    admin = accounts["deployer"]
    for function in (
        chain.hub.functions.setCharity(accounts["charity"].address, True),
        chain.hub.functions.setOfficer(accounts["officer"].address, True),
    ):
        send(w3, admin, function.build_transaction({"from": admin.address}))

    # The example Passport names Anvil account 4 as its officer.
    passport = Passport.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    assert passport.officer.address == accounts["officer"].address
    config = ProjectConfig.from_passport(passport, accounts["charity"].address)
    cid = "bafkreie5example"
    message = launch_message(passport, config, passport.digest(), cid)
    domain = eip712.Domain(w3.eth.chain_id, deployment.hub)
    signature = eip712.sign(accounts["charity"].key, domain, "ProjectLaunch", message)

    relayer = accounts["relayer"]
    create = chain.factory.functions.createProject(
        config.abi_value(), passport.digest(), cid, signature
    )
    send(w3, relayer, create.build_transaction({"from": relayer.address}))

    escrow_address = chain.hub.functions.escrowOf(passport.project_id.bytes).call()
    escrow = chain.escrow(escrow_address)
    assert escrow.functions.milestoneCount().call() == 3
    entry = chain.registry.functions.current(passport.project_id.bytes).call()
    assert entry[1] == passport.digest()
    assert entry[2] == config.contractor_hash
