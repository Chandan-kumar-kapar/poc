from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.schemas import Page
from app.db.session import get_session
from app.modules.auth.deps import require_permission
from app.modules.clients.schemas import ClientSummary
from app.modules.policies.models import PolicyStatus
from app.modules.policies.schemas import (
    BeneficiarySchema,
    PolicyDetail,
    PolicyDocumentSchema,
    PolicyListItem,
    PolicyStatusInfo,
    PolicyTimeline,
    PremiumInfo,
)
from app.modules.policies import service as policy_service

router = APIRouter(prefix="/policies", tags=["policies"])

_SortBy = Literal[
    "issue_date", "maturity_date", "policy_number", "client_name",
    "premium_amount", "coverage_amount", "status",
]
_SortDir = Literal["asc", "desc"]


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
    client_name: Optional[str] = Query(None),
    issue_date_from: Optional[date] = Query(None),
    issue_date_to: Optional[date] = Query(None),
    sort_by: _SortBy = Query("issue_date"),
    sort_dir: _SortDir = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[PolicyListItem]:
    items, total = await policy_service.search_policies(
        db,
        q=q,
        status=status_filter,
        product_type=product_type,
        client_id=client_id,
        client_name=client_name,
        issue_date_from=issue_date_from,
        issue_date_to=issue_date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return Page[PolicyListItem](
        items=[PolicyListItem.model_validate(p) for p in items],
        page=page,
        page_size=page_size,
        total=total,
    )


async def _get_policy_or_404(db: AsyncSession, policy_id: uuid.UUID):
    p = await policy_service.get_policy(db, policy_id)
    if p is None:
        raise AppError("not_found", "Policy not found.", status.HTTP_404_NOT_FOUND)
    return p


@router.get(
    "/{policy_id}",
    response_model=PolicyDetail,
    dependencies=[Depends(require_permission("policy:view"))],
)
async def get_policy(
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyDetail:
    p = await _get_policy_or_404(db, policy_id)
    return PolicyDetail(
        id=p.id,
        policy_number=p.policy_number,
        product_type=p.product_type,
        status=p.status,
        start_date=p.start_date,
        end_date=p.end_date,
        coverage_amount=p.coverage_amount,
        client=ClientSummary(
            id=p.client.id,
            client_code=p.client.client_code,
            full_name=p.client.full_name,
        ),
        timeline=PolicyTimeline(
            issued=p.start_date, today=date.today(), matures=p.end_date
        ),
    )


@router.get(
    "/{policy_id}/premium",
    response_model=PremiumInfo,
    dependencies=[Depends(require_permission("policy:view"))],
)
async def get_policy_premium(
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PremiumInfo:
    p = await _get_policy_or_404(db, policy_id)
    return PremiumInfo.model_validate(p, from_attributes=True)


@router.get(
    "/{policy_id}/status",
    response_model=PolicyStatusInfo,
    dependencies=[Depends(require_permission("policy:view"))],
)
async def get_policy_status(
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> PolicyStatusInfo:
    p = await _get_policy_or_404(db, policy_id)
    return PolicyStatusInfo(status=p.status)


@router.get(
    "/{policy_id}/beneficiaries",
    response_model=list[BeneficiarySchema],
    dependencies=[Depends(require_permission("policy:view"))],
)
async def get_policy_beneficiaries(
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[BeneficiarySchema]:
    p = await _get_policy_or_404(db, policy_id)
    return [BeneficiarySchema.model_validate(b) for b in p.beneficiaries]


@router.get(
    "/{policy_id}/documents",
    response_model=list[PolicyDocumentSchema],
    dependencies=[Depends(require_permission("policy:view"))],
)
async def get_policy_documents(
    policy_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> list[PolicyDocumentSchema]:
    p = await _get_policy_or_404(db, policy_id)
    return [PolicyDocumentSchema.model_validate(d) for d in p.documents]
