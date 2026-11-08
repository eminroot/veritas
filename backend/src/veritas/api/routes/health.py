"""Health checks for the load balancer and the deploy scripts."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from veritas.api.deps import DbSession
from veritas.services.errors import Unavailable

router = APIRouter(tags=["health"])


class Live(BaseModel):
    status: str = "ok"


class Ready(BaseModel):
    status: str = "ready"
    postgis: str


@router.get("/health")
def liveness() -> Live:
    """The process is up. Says nothing about the database."""
    return Live()


@router.get("/health/ready")
def readiness(db: DbSession) -> Ready:
    """The database answers and has PostGIS, so requests can be served."""
    try:
        db.execute(text("SELECT 1"))
        postgis = db.scalar(text("SELECT postgis_version()"))
    except SQLAlchemyError:
        raise Unavailable("not_ready", "The database is not reachable or not set up.") from None
    return Ready(postgis=str(postgis))
