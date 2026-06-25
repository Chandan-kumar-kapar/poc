from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client, ClientStatus
from app.modules.policies.models import Beneficiary, Policy


async def search_clients(
    db: AsyncSession,
    *,
    q: Optional[str] = None,
    client_code: Optional[str] = None,
    policy_number: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    date_of_birth: Optional[date] = None,
    mobile: Optional[str] = None,
    status: Optional[ClientStatus] = None,
    page: int,
    page_size: int,
) -> tuple[list[Client], int]:
    stmt = select(Client)
    count_stmt = select(func.count(func.distinct(Client.id))).select_from(Client)

    if policy_number:
        stmt = stmt.join(Policy, Policy.client_id == Client.id)
        count_stmt = count_stmt.join(Policy, Policy.client_id == Client.id)

    conditions = []
    if q:
        like = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(Client.first_name).like(like),
                func.lower(Client.last_name).like(like),
                func.lower(Client.email).like(like),
                func.lower(Client.client_code).like(like),
            )
        )
    if client_code:
        conditions.append(func.lower(Client.client_code).like(f"%{client_code.lower()}%"))
    if policy_number:
        conditions.append(
            func.lower(Policy.policy_number).like(f"%{policy_number.lower()}%")
        )
    if first_name:
        conditions.append(func.lower(Client.first_name).like(f"%{first_name.lower()}%"))
    if last_name:
        conditions.append(func.lower(Client.last_name).like(f"%{last_name.lower()}%"))
    if date_of_birth is not None:
        conditions.append(Client.date_of_birth == date_of_birth)
    if mobile:
        conditions.append(Client.phone.like(f"%{mobile}%"))
    if status is not None:
        conditions.append(Client.status == status)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.distinct()
        .order_by(Client.last_name.asc(), Client.first_name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


async def get_client(db: AsyncSession, client_id: uuid.UUID) -> Optional[Client]:
    result = await db.execute(select(Client).where(Client.id == client_id))
    return result.scalar_one_or_none()


async def get_client_policies(db: AsyncSession, client_id: uuid.UUID) -> list[Policy]:
    result = await db.execute(
        select(Policy)
        .where(Policy.client_id == client_id)
        .order_by(Policy.start_date.desc())
    )
    return list(result.scalars().all())


async def get_client_beneficiaries(
    db: AsyncSession, client_id: uuid.UUID
) -> list[tuple[Beneficiary, str]]:
    """Beneficiaries belong to a Policy, not a Client directly — this
    aggregates them across all of the client's policies."""
    result = await db.execute(
        select(Beneficiary, Policy.policy_number)
        .join(Policy, Beneficiary.policy_id == Policy.id)
        .where(Policy.client_id == client_id)
        .order_by(Beneficiary.percentage.desc())
    )
    return [(b, policy_number) for b, policy_number in result.all()]
