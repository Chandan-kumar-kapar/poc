from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.core.errors import AppError
from app.db.session import get_session
from app.models.domain import PolicyStatus
from app.schemas.domain import (
    ClientSummary,
    Page,
    PolicyDetail,
    PolicyListItem,
)
from app.services import policy as policy_service

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get(
    "",
    response_model=Page[PolicyListItem],
    dependencies=[Depends(require_permission("policy:view"))],
)
async def list_policies(
    db: Annotated[AsyncSession, Depends(get_session)],
    q: Optional[str] = Query(None, description="Match policy_number (partial)"),
    status_filter: Optional[PolicyStatus] = Query(None, alias="status"),
    product_type: Optional[str] = Query(None),
    client_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[PolicyListItem]:
    items, total = await policy_service.search_policies(
        db,
        q=q,
        status=status_filter,
        product_type=product_type,
        client_id=client_id,
        page=page,
        page_size=page_size,
    )
    return Page[PolicyListItem](
        items=[PolicyListItem.model_validate(p) for p in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/{policy_id}",
    response_model=PolicyDetail,
    dependencies=[Depends(require_permission("policy:view"))],
)
async def get_policy(
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyDetail:
    p = await policy_service.get_policy(db, policy_id)
    if p is None:
        raise AppError("not_found", "Policy not found.", status.HTTP_404_NOT_FOUND)
    detail = PolicyDetail.model_validate(p)
    detail.client = ClientSummary(
        id=p.client.id,
        client_code=p.client.client_code,
        full_name=p.client.full_name,
    )
    return detail
