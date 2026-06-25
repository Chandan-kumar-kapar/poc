from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    String,
    func,
)
from app.db.types import GUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ClientStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RiskProfile(str, enum.Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(), primary_key=True, default=uuid.uuid4
    )
    client_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), index=True)
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    gender: Mapped[Optional[Gender]] = mapped_column(
        Enum(Gender, name="gender"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Only the last 4 digits are ever persisted — the full SSN/PAN is never
    # stored since no workflow here needs it (read-only search/detail views).
    ssn_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    risk_profile: Mapped[RiskProfile] = mapped_column(
        Enum(RiskProfile, name="risk_profile"), default=RiskProfile.LOW
    )
    address_line1: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[ClientStatus] = mapped_column(
        Enum(ClientStatus, name="client_status"), default=ClientStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    policies: Mapped[List["Policy"]] = relationship(
        back_populates="client", lazy="selectin"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def ssn_masked(self) -> Optional[str]:
        return f"•••••{self.ssn_last4}" if self.ssn_last4 else None

    @property
    def policy_count(self) -> int:
        return len(self.policies)

    @property
    def full_address(self) -> Optional[str]:
        if not self.address_line1:
            return None
        parts = [self.address_line1]
        city_state = ", ".join(p for p in (self.city, self.state) if p)
        if city_state:
            parts.append(city_state)
        if self.postal_code:
            parts.append(self.postal_code)
        return ", ".join(parts)
