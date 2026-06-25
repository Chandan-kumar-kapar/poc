from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from app.db.types import GUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.modules.clients.models import Client  # noqa: F401  (relationship target)


class PolicyStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LAPSED = "LAPSED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"


class BeneficiaryRelationship(str, enum.Enum):
    SPOUSE = "SPOUSE"
    CHILD = "CHILD"
    PARENT = "PARENT"
    SIBLING = "SIBLING"
    OTHER = "OTHER"


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), primary_key=True, default=uuid.uuid4
    )
    policy_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    product_type: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[PolicyStatus] = mapped_column(
        Enum(PolicyStatus, name="policy_status"),
        default=PolicyStatus.ACTIVE,
        index=True,
    )
    premium_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    coverage_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    underwriter: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    agent_code: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    payment_frequency: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    next_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_paid_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    total_paid_to_date: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="policies", lazy="selectin")
    beneficiaries: Mapped[List["Beneficiary"]] = relationship(
        back_populates="policy", lazy="selectin", cascade="all, delete-orphan",
        order_by="Beneficiary.percentage.desc()",
    )
    documents: Mapped[List["PolicyDocument"]] = relationship(
        back_populates="policy", lazy="selectin", cascade="all, delete-orphan",
        order_by="PolicyDocument.created_at.desc()",
    )

    @property
    def client_name(self) -> str:
        return self.client.full_name

    @property
    def term_progress_years(self) -> Optional[float]:
        if self.end_date is None:
            return None
        elapsed_days = (date.today() - self.start_date).days
        return round(max(0.0, elapsed_days / 365), 1)

    @property
    def term_years(self) -> Optional[float]:
        if self.end_date is None:
            return None
        return round((self.end_date - self.start_date).days / 365, 1)


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), primary_key=True, default=uuid.uuid4
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    relationship_type: Mapped[BeneficiaryRelationship] = mapped_column(
        Enum(BeneficiaryRelationship, name="beneficiary_relationship")
    )
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    policy: Mapped["Policy"] = relationship(back_populates="beneficiaries")


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), primary_key=True, default=uuid.uuid4
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    doc_type: Mapped[str] = mapped_column(String(40))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    policy: Mapped["Policy"] = relationship(back_populates="documents")
