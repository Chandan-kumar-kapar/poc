from __future__ import annotations

import asyncio
import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.passwords import hash_password
from app.db.session import AsyncSessionLocal
from app.models.auth import Permission, Role, User
from app.models.domain import Client, ClientStatus, Policy, PolicyStatus

settings = get_settings()

PERMISSIONS = [
    ("client:view", "View clients"),
    ("policy:view", "View policies"),
]

ROLES = {
    "Admin": [p[0] for p in PERMISSIONS],
    "User": ["client:view", "policy:view"],
}

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael",
    "Linda", "David", "Elizabeth", "William", "Barbara", "Richard", "Susan",
    "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen", "Aisha",
    "Mohammed", "Wei", "Priya", "Carlos",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Patel", "Nguyen", "Kim", "Chen", "Singh",
]
PRODUCTS = ["AUTO", "HOME", "LIFE", "HEALTH"]


async def seed_rbac(db) -> dict[str, Role]:
    perms: dict[str, Permission] = {}
    for name, desc in PERMISSIONS:
        existing = (
            await db.execute(select(Permission).where(Permission.name == name))
        ).scalar_one_or_none()
        if existing is None:
            existing = Permission(name=name, description=desc)
            db.add(existing)
            await db.flush()
        perms[name] = existing

    roles: dict[str, Role] = {}
    for role_name, perm_names in ROLES.items():
        existing = (
            await db.execute(select(Role).where(Role.name == role_name))
        ).scalar_one_or_none()
        if existing is None:
            existing = Role(name=role_name, description=f"{role_name} role")
            existing.permissions = [perms[p] for p in perm_names]
            db.add(existing)
            await db.flush()
        roles[role_name] = existing
    return roles


async def seed_users(db, roles: dict[str, Role]) -> None:
    accounts = [
        (settings.seed_admin_email, settings.seed_admin_password, "Admin"),
        (settings.seed_user_email, settings.seed_user_password, "User"),
    ]
    for email, password, role_name in accounts:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            u = User(
                email=email,
                password_hash=hash_password(password),
                email_verified=True,
                is_active=True,
            )
            u.roles.append(roles[role_name])
            db.add(u)
    await db.flush()


async def seed_domain(db) -> None:
    existing = (await db.execute(select(Client))).scalars().first()
    if existing is not None:
        return  # already seeded

    rng = random.Random(42)
    clients: list[Client] = []
    for i in range(1, 21):
        fn = rng.choice(FIRST_NAMES)
        ln = rng.choice(LAST_NAMES)
        c = Client(
            client_code=f"CLT-{i:04d}",
            first_name=fn,
            last_name=ln,
            email=f"{fn.lower()}.{ln.lower()}{i}@example.com",
            phone=f"+1-555-{rng.randint(1000, 9999)}",
            date_of_birth=date(rng.randint(1955, 2002), rng.randint(1, 12), rng.randint(1, 28)),
            status=rng.choice([ClientStatus.ACTIVE] * 4 + [ClientStatus.INACTIVE]),
        )
        clients.append(c)
        db.add(c)
    await db.flush()

    pol_num = 1
    for _ in range(50):
        c = rng.choice(clients)
        start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 900))
        term_years = rng.choice([1, 2, 3])
        p = Policy(
            policy_number=f"POL-{pol_num:05d}",
            client_id=c.id,
            product_type=rng.choice(PRODUCTS),
            status=rng.choice(
                [PolicyStatus.ACTIVE] * 3
                + [PolicyStatus.LAPSED, PolicyStatus.CANCELLED, PolicyStatus.PENDING]
            ),
            premium_amount=Decimal(rng.randint(20000, 500000)) / 100,
            currency="USD",
            start_date=start,
            end_date=start + timedelta(days=365 * term_years),
        )
        pol_num += 1
        db.add(p)
    await db.flush()


async def run() -> None:
    async with AsyncSessionLocal() as db:
        roles = await seed_rbac(db)
        await seed_users(db, roles)
        await seed_domain(db)
        await db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(run())
