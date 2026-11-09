"""Every table, imported here so Base.metadata knows them all."""

# Registered so Base.metadata and the migrations see them. Import them from their modules.
from veritas.db.models import chain as chain
from veritas.db.models import decisions as decisions
from veritas.db.models import evidence as evidence
from veritas.db.models import money as money
from veritas.db.models.accounts import (
    AuthSession,
    ChallengePurpose,
    Device,
    DeviceChallenge,
    LoginCode,
    PasswordReset,
    Platform,
    User,
)
from veritas.db.models.organisations import (
    DOCUMENT_TYPES,
    Charity,
    CharityMember,
    CharityStatus,
    Contractor,
    ContractorStatus,
    DocumentKind,
    KybDocument,
    MemberRole,
    Officer,
    OfficerStatus,
    OwnerType,
    RegistryStatus,
)
from veritas.db.models.projects import (
    BudgetLine,
    Milestone,
    MilestoneStatus,
    PassportStatus,
    PassportVersion,
    Project,
    ProjectStatus,
    Site,
)

__all__ = [
    "DOCUMENT_TYPES",
    "AuthSession",
    "BudgetLine",
    "ChallengePurpose",
    "Charity",
    "CharityMember",
    "CharityStatus",
    "Contractor",
    "ContractorStatus",
    "Device",
    "DeviceChallenge",
    "DocumentKind",
    "KybDocument",
    "LoginCode",
    "MemberRole",
    "Milestone",
    "MilestoneStatus",
    "Officer",
    "OfficerStatus",
    "OwnerType",
    "PassportStatus",
    "PassportVersion",
    "PasswordReset",
    "Platform",
    "Project",
    "ProjectStatus",
    "RegistryStatus",
    "Site",
    "User",
]

from veritas.mocks import models as mock_models  # noqa: E402  (after the base tables)

__all__ += ["chain", "decisions", "mock_models", "money"]
