from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.modules.clients.schemas import ClientSummary
from app.modules.policies.models import PolicyStatus


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
