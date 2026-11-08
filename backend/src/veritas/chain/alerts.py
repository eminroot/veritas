"""Alerts: problems a person has to look at.

Raised when the chain and the database disagree, when a transaction fails or gets stuck,
and when the daily reconciliation does not balance. Each one is also logged at the matching
level, so it reaches whatever watches the logs before anyone opens the table.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from veritas.db.models.chain import Alert, AlertSeverity

log = logging.getLogger("veritas.alerts")

_LEVELS = {
    AlertSeverity.INFO: logging.INFO,
    AlertSeverity.WARNING: logging.WARNING,
    AlertSeverity.CRITICAL: logging.CRITICAL,
}


def raise_alert(
    session: Session,
    *,
    kind: str,
    message: str,
    severity: str = AlertSeverity.WARNING,
    details: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
) -> Alert:
    """Record an alert. With a dedupe key, the same problem seen again is recorded once."""
    severity = AlertSeverity(severity)
    log.log(_LEVELS[severity], "%s: %s", kind, message)
    values = {
        "severity": str(severity),
        "kind": kind,
        "message": message,
        "details": details or {},
        "dedupe_key": dedupe_key,
    }
    if dedupe_key is None:
        alert = Alert(**values)
        session.add(alert)
        session.flush()
        return alert
    session.execute(
        insert(Alert).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    return session.scalars(select(Alert).where(Alert.dedupe_key == dedupe_key)).one()
