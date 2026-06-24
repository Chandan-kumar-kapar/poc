from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict
from app.core.email_types import EmailStrLoose as EmailStr

from app.modules.clients.models import ClientStatus


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
