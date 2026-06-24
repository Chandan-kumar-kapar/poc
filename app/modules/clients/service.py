from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client, ClientStatus


async def search_clients(
    db: AsyncSession,
    *,
    q: Optional[str],
    status: Optional[ClientStatus],
    page: int,
    page_size: int,
) -> tuple[list[Client], int]:
    stmt = select(Client)
    count_stmt = select(func.count()).select_from(Client)

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
    if status is not None:
        conditions.append(Client.status == status)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Client.last_name.asc(), Client.first_name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())
    return items, total


async def get_client(db: AsyncSession, client_id: uuid.UUID) -> Optional[Client]:
    result = await db.execute(select(Client).where(Client.id == client_id))
    return result.scalar_one_or_none()
