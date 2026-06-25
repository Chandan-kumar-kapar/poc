from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict
from app.core.email_types import EmailStrLoose as EmailStr

from app.modules.clients.models import ClientStatus, Gender
from app.modules.policies.models import BeneficiaryRelationship, PolicyStatus


class ClientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_code: str
    full_name: str


class ClientListItem(BaseModel):
    """Matches the Client Search results table: Client ID, Name, DOB, Mobile,
    Policies, Status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_code: str
    full_name: str
    date_of_birth: Optional[date]
    phone: Optional[str]
    policy_count: int
    status: ClientStatus


class ClientDetail(BaseModel):
    """Personal + contact details only — beneficiaries and linked policies
    are fetched on demand via their own endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_code: str
    full_name: str
    gender: Optional[Gender]
    date_of_birth: Optional[date]
    ssn_masked: Optional[str]
    email: EmailStr
    phone: Optional[str]
    full_address: Optional[str]


class ClientBeneficiary(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    policy_number: str
    name: str
    relationship_type: BeneficiaryRelationship
    percentage: Decimal
    is_primary: bool


class LinkedPolicySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    product_type: str
    status: PolicyStatus
    start_date: date
    end_date: Optional[date]
    next_due_date: Optional[date]
