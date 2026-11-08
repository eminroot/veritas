"""The declarative base every table hangs off, and the column rules they share.

Constraint names come from one naming convention, so a migration can refer to a
constraint by name and the name is the same on every database. Statuses are text
with a CHECK, not PostgreSQL enum types, because adding a value to a CHECK is an
ordinary migration and adding one to an enum type is not.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, CheckConstraint, DateTime, MetaData, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}

Qapik = Annotated[int, mapped_column(BigInteger)]
"""Money: an int number of qəpik, always BIGINT."""


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        str: Text(),
        datetime: DateTime(timezone=True),
    }


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, sort_order=-10)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), sort_order=10)


class Timestamps(CreatedAt):
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), sort_order=11
    )


def one_of(column: str, values: Iterable[str]) -> CheckConstraint:
    """CHECK that a text column holds one of `values`. Named ck_<table>_<column>."""
    allowed = list(values)
    if any("'" in value for value in allowed):
        raise ValueError("allowed values cannot contain quotes")
    listed = ", ".join(f"'{value}'" for value in allowed)
    return CheckConstraint(f"{column} IN ({listed})", name=column)


def byte_length(column: str, size: int) -> CheckConstraint:
    """CHECK that a BYTEA column, when set, holds exactly `size` bytes."""
    return CheckConstraint(f"octet_length({column}) = {size}", name=f"{column}_length")


def evm_address(column: str) -> CheckConstraint:
    """CHECK the shape of an address. The checksum itself is the application's job."""
    return CheckConstraint(f"{column} ~ '^0x[0-9a-fA-F]{{40}}$'", name=f"{column}_format")


def az_phone(column: str) -> CheckConstraint:
    """CHECK a phone number is in the form normalize_az_phone gives: +994 and 9 digits."""
    return CheckConstraint(rf"{column} ~ '^\+994[1-9][0-9]{{8}}$'", name=f"{column}_format")


def voen(column: str = "voen") -> CheckConstraint:
    return CheckConstraint(f"{column} ~ '^[0-9]{{10}}$'", name=f"{column}_format")
