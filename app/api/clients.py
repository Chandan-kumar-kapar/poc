from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.core.errors import AppError
from app.db.session import get_session
from app.models.domain import ClientStatus
from app.schemas.domain import ClientDetail, ClientListItem, Page
from app.services import client as client_service

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get(
    "",
    response_model=Page[ClientListItem],
    dependencies=[Depends(require_permission("client:view"))],
)
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_session)],
    q: Optional[str] = Query(None, description="Match name / email / client_code"),
    status_filter: Optional[ClientStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[ClientListItem]:
    items, total = await client_service.search_clients(
        db, q=q, status=status_filter, page=page, page_size=page_size
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
