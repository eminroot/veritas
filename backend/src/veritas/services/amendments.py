"""Amending a live project's Passport: the charity proposes, the donors decide.

Once a project has launched, its Passport changes only by amendment. The charity drafts the
next version as usual and signs an Amendment message over its hash and the contractor it
names. The registry opens a donor vote, and only if the vote passes does the chain record the
new version; the indexer then publishes the draft, byte for byte the version the donors
approved. An amendment can change the documents and the contractor, never the milestone
amounts, deadlines or decision rules, which the escrow copied at launch. A draft that tries
to is refused here, before anyone signs it.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.alerts import raise_alert
from veritas.chain.outbox import enqueue
from veritas.chain.project import ProjectConfig
from veritas.chain.runtime import Chain
from veritas.chain.signatures import signed_by
from veritas.core.hashing import sha256
from veritas.db.models import Charity, PassportVersion, Project, ProjectStatus
from veritas.db.models.chain import ChainEvent, ChainOutbox, OutboxStatus
from veritas.passport import Passport, load_passport
from veritas.services.cid import raw_cid
from veritas.services.errors import Conflict, Forbidden, NotFound, Unprocessable
from veritas.services.passports import (
    current_draft,
    draft_problems,
    publish_version,
    published_version,
)


def amendment_pending(session: Session, project: Project) -> bool:
    """True while a proposed amendment waits for the chain or for its vote to end."""
    proposal = session.scalars(
        select(ChainOutbox)
        .where(ChainOutbox.project_id == project.id, ChainOutbox.kind == "propose_amendment")
        .order_by(ChainOutbox.id.desc())
    ).first()
    if proposal is None or proposal.status in (OutboxStatus.FAILED, OutboxStatus.CANCELLED):
        return False
    registry_events = select(ChainEvent.id).where(
        ChainEvent.project_id == project.id, ChainEvent.contract == "PassportRegistry"
    )
    recorded = session.scalar(
        registry_events.where(
            ChainEvent.event == "PassportRecorded",
            ChainEvent.args["version"].as_integer() == proposal.args[1],
        )
    )
    rejected = proposal.mined_block is not None and session.scalar(
        registry_events.where(
            ChainEvent.event == "AmendmentRejected",
            ChainEvent.block_number >= proposal.mined_block,
        )
    )
    return recorded is None and not rejected


def _amendment(session: Session, project: Project) -> tuple[dict[str, Any], Passport, Charity]:
    if project.status != ProjectStatus.LIVE:
        raise Conflict("not_live", "Only a live project's Passport is amended.")
    draft = current_draft(session, project)
    if draft is None:
        raise NotFound("no_draft", "Draft the next version of the Passport first.")
    passport, problems = draft_problems(session, project, draft)
    if passport is None or problems:
        raise Unprocessable(
            "passport_invalid",
            "The draft has problems to fix before it can be proposed.",
            details=list(problems),
        )
    charity = session.get_one(Charity, project.charity_id)
    current = load_passport(published_version(session, project).canonical_bytes)
    signer = project.charity_signer or charity.signer_address or ""
    before = ProjectConfig.from_passport(current, signer)
    after = ProjectConfig.from_passport(passport, signer)
    if dataclasses.replace(after, contractor_hash=before.contractor_hash) != before:
        raise Unprocessable(
            "amendment_changes_rules",
            "An amendment can change the documents and the contractor, not the milestone "
            "amounts, deadlines or decision rules the escrow enforces.",
        )
    data = passport.canonical_bytes()
    message = {
        "projectId": project.id.bytes,
        "version": passport.version,
        "passportHash": sha256(data),
        "cid": raw_cid(data),
        "contractorHash": after.contractor_hash,
    }
    return message, passport, charity


def amendment_message(session: Session, project: Project, chain: Chain) -> dict[str, Any]:
    """The Amendment message for the charity's key to sign."""
    if amendment_pending(session, project):
        raise Conflict("amendment_pending", "An amendment is already waiting for its vote.")
    message, _, _ = _amendment(session, project)
    return eip712.typed_data(chain.domain, "Amendment", message)


def propose_amendment(
    session: Session, chain: Chain, project: Project, signature: bytes
) -> ChainOutbox:
    if amendment_pending(session, project):
        raise Conflict("amendment_pending", "An amendment is already waiting for its vote.")
    message, _, _ = _amendment(session, project)
    # The registry checks the escrow's charity: the key the project was launched with.
    if not signed_by(
        chain.w3, chain.domain, "Amendment", message, signature, project.charity_signer
    ):
        raise Forbidden(
            "bad_signature",
            f"The amendment is not signed by the key this project was launched with, "
            f"{project.charity_signer}.",
        )
    return enqueue(
        session,
        kind="propose_amendment",
        contract="PassportRegistry",
        function="proposeAmendment",
        args=[
            project.id.bytes,
            message["version"],
            message["passportHash"],
            message["cid"],
            message["contractorHash"],
            signature,
        ],
        dedupe_key=f"propose_amendment:{project.id}:{message['passportHash'].hex()}",
        project_id=project.id,
    )


def on_passport_recorded(session: Session, event: ChainEvent) -> None:
    """The donors approved an amendment: publish exactly the draft they voted on."""
    version = event.args["version"]
    if version == 1 or event.project_id is None:
        return  # version 1 is the launch, handled with ProjectCreated
    project = session.get(Project, event.project_id, with_for_update=True)
    draft = session.scalars(
        select(PassportVersion).where(
            PassportVersion.project_id == event.project_id, PassportVersion.version == version
        )
    ).first()
    passport, problems = (None, []) if draft is None else draft_problems(session, project, draft)
    recorded = bytes.fromhex(event.args["passportHash"][2:])
    if passport is None or problems or sha256(passport.canonical_bytes()) != recorded:
        raise_alert(
            session,
            kind="event_mismatch",
            severity="critical",
            message=f"Passport version {version} on-chain is not the draft this database holds",
            details={"project_id": str(event.project_id), "on_chain": event.args["passportHash"]},
            dedupe_key=f"amendment_mismatch:{event.tx_hash.hex()}:{event.log_index}",
        )
        return
    publish_version(session, project, draft, passport, published_by=None, charity_signature=None)
