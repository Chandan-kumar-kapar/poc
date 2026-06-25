from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.clients.models import Client
from app.modules.policies.models import Policy, PolicyStatus

_SORTABLE_FIELDS = {
    "policy_number": Policy.policy_number,
    "issue_date": Policy.start_date,
    "maturity_date": Policy.end_date,
    "client_name": Client.last_name,
    "premium_amount": Policy.premium_amount,
    "coverage_amount": Policy.coverage_amount,
    "status": Policy.status,
}


async def search_policies(
    db: AsyncSession,
    *,
    q: Optional[str] = None,
    status: Optional[PolicyStatus] = None,
    product_type: Optional[str] = None,
    client_id: Optional[uuid.UUID] = None,
    client_name: Optional[str] = None,
    issue_date_from: Optional[date] = None,
    issue_date_to: Optional[date] = None,
    sort_by: str = "issue_date",
    sort_dir: str = "desc",
    page: int,
    page_size: int,
) -> tuple[list[Policy], int]:
    needs_client_join = client_name is not None or sort_by == "client_name"

    stmt = select(Policy)
    count_stmt = select(func.count(func.distinct(Policy.id))).select_from(Policy)
    if needs_client_join:
        stmt = stmt.join(Client, Policy.client_id == Client.id)
        count_stmt = count_stmt.join(Client, Policy.client_id == Client.id)

    conditions = []
    if q:
        conditions.append(func.lower(Policy.policy_number).like(f"%{q.lower()}%"))
    if status is not None:
        conditions.append(Policy.status == status)
    if product_type:
        conditions.append(func.lower(Policy.product_type) == product_type.lower())
    if client_id is not None:
        conditions.append(Policy.client_id == client_id)
    if client_name:
        like = f"%{client_name.lower()}%"
        conditions.append(
            func.lower(Client.first_name + " " + Client.last_name).like(like)
        )
    if issue_date_from is not None:
        conditions.append(Policy.start_date >= issue_date_from)
    if issue_date_to is not None:
        conditions.append(Policy.start_date <= issue_date_to)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()

    sort_col = _SORTABLE_FIELDS.get(sort_by, Policy.start_date)
    order = desc(sort_col) if sort_dir == "desc" else asc(sort_col)
    stmt = (
        stmt.order_by(order)
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
