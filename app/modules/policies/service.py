from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.policies.models import Policy, PolicyStatus


async def search_policies(
    db: AsyncSession,
    *,
    q: Optional[str],
    status: Optional[PolicyStatus],
    product_type: Optional[str],
    client_id: Optional[uuid.UUID],
    page: int,
    page_size: int,
) -> tuple[list[Policy], int]:
    stmt = select(Policy)
    count_stmt = select(func.count()).select_from(Policy)

    conditions = []
    if q:
        conditions.append(func.lower(Policy.policy_number).like(f"%{q.lower()}%"))
    if status is not None:
        conditions.append(Policy.status == status)
    if product_type:
        conditions.append(func.lower(Policy.product_type) == product_type.lower())
    if client_id is not None:
        conditions.append(Policy.client_id == client_id)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Policy.start_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


async def get_policy(db: AsyncSession, policy_id: uuid.UUID) -> Optional[Policy]:
    result = await db.execute(
        select(Policy)
        .where(Policy.id == policy_id)
        .options(selectinload(Policy.client))
    )
    return result.scalar_one_or_none()
