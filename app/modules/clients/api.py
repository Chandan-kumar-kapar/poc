from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.schemas import Page
from app.db.session import get_session
from app.modules.auth.deps import require_permission
from app.modules.clients.models import ClientStatus
from app.modules.clients.schemas import (
    ClientBeneficiary,
    ClientDetail,
    ClientListItem,
    LinkedPolicySummary,
)
from app.modules.clients import service as client_service

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get(
    "",
    response_model=Page[ClientListItem],
    dependencies=[Depends(require_permission("client:view"))],
)
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_session)],
    q: Optional[str] = Query(None, description="Match name / email / client_code"),
    client_code: Optional[str] = Query(None),
    policy_number: Optional[str] = Query(None),
    first_name: Optional[str] = Query(None),
    last_name: Optional[str] = Query(None),
    date_of_birth: Optional[date] = Query(None),
    mobile: Optional[str] = Query(None),
    status_filter: Optional[ClientStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[ClientListItem]:
    items, total = await client_service.search_clients(
        db,
        q=q,
        client_code=client_code,
        policy_number=policy_number,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=date_of_birth,
        mobile=mobile,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return Page[ClientListItem](
        items=[ClientListItem.model_validate(c) for c in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/{client_id}",
    response_model=ClientDetail,
    dependencies=[Depends(require_permission("client:view"))],
)
async def get_client(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> ClientDetail:
    c = await client_service.get_client(db, client_id)
    if c is None:
        raise AppError("not_found", "Client not found.", status.HTTP_404_NOT_FOUND)
    return ClientDetail.model_validate(c)


@router.get(
    "/{client_id}/beneficiaries",
    response_model=list[ClientBeneficiary],
    dependencies=[Depends(require_permission("client:view"))],
)
async def get_client_beneficiaries(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[ClientBeneficiary]:
    c = await client_service.get_client(db, client_id)
    if c is None:
        raise AppError("not_found", "Client not found.", status.HTTP_404_NOT_FOUND)
    rows = await client_service.get_client_beneficiaries(db, client_id)
    return [
        ClientBeneficiary(
            id=b.id,
            policy_id=b.policy_id,
            policy_number=policy_number,
            name=b.name,
            relationship_type=b.relationship_type,
            percentage=b.percentage,
            is_primary=b.is_primary,
        )
        for b, policy_number in rows
    ]


@router.get(
    "/{client_id}/policies",
    response_model=list[LinkedPolicySummary],
    dependencies=[Depends(require_permission("client:view"))],
)
async def get_client_linked_policies(
    client_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[LinkedPolicySummary]:
    c = await client_service.get_client(db, client_id)
    if c is None:
        raise AppError("not_found", "Client not found.", status.HTTP_404_NOT_FOUND)
    policies = await client_service.get_client_policies(db, client_id)
    return [LinkedPolicySummary.model_validate(p) for p in policies]
