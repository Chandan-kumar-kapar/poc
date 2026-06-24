from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict
from app.core.email_types import EmailStrLoose as EmailStr

from app.models.domain import ClientStatus, PolicyStatus

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    page: int
    page_size: int
    total: int


class ClientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_code: str
    full_name: str


class ClientListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_code: str
    first_name: str
    last_name: str
    email: EmailStr
    status: ClientStatus


class ClientDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_code: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str]
    date_of_birth: Optional[date]
    status: ClientStatus
    created_at: datetime
    updated_at: datetime


class PolicyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    client_id: uuid.UUID
    product_type: str
    status: PolicyStatus
    premium_amount: Decimal
    currency: str
    start_date: date
    end_date: Optional[date]


class PolicyDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    policy_number: str
    client_id: uuid.UUID
    product_type: str
    status: PolicyStatus
    premium_amount: Decimal
    currency: str
    start_date: date
    end_date: Optional[date]
    created_at: datetime
    updated_at: datetime
    client: ClientSummary
