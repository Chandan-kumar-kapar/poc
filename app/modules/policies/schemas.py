from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.modules.clients.schemas import ClientSummary
from app.modules.policies.models import BeneficiaryRelationship, PolicyStatus

ALL_POLICY_STATUSES = ["ACTIVE", "LAPSED", "SURRENDERED", "MATURED"]


class BeneficiarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    relationship_type: BeneficiaryRelationship
    percentage: Decimal
    is_primary: bool


class PolicyDocumentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    doc_type: str
    file_size_bytes: int
    created_at: datetime


class PolicyListItem(BaseModel):
    """Matches the Policies Explorer results table: Policy No., Type, Client,
    Status, Premium, Issue Date, Maturity."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    client_id: uuid.UUID
    client_name: str
    product_type: str
    status: PolicyStatus
    premium_amount: Decimal
    currency: str
    start_date: date
    end_date: Optional[date]


class PolicyTimeline(BaseModel):
    issued: date
    today: date
    matures: Optional[date]


class PolicyDetail(BaseModel):
    """Core policy facts — premium info, status, beneficiaries, and documents
    are fetched on demand via their own endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    product_type: str
    status: PolicyStatus
    start_date: date
    end_date: Optional[date]
    coverage_amount: Optional[Decimal]
    client: ClientSummary
    timeline: PolicyTimeline


class PremiumInfo(BaseModel):
    premium_amount: Decimal
    currency: str
    payment_frequency: Optional[str]
    next_due_date: Optional[date]
    last_paid_date: Optional[date]
    total_paid_to_date: Optional[Decimal]
    term_progress_years: Optional[float]
    term_years: Optional[float]


class PolicyStatusInfo(BaseModel):
    status: PolicyStatus
    all_statuses: List[str] = ALL_POLICY_STATUSES
