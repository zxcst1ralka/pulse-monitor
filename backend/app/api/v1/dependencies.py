from typing import Annotated, TypeVar
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.db.session import get_db
from app.models import Base, User

Db = Annotated[AsyncSession, Depends(get_db)]
Account = Annotated[User, Depends(current_user)]
PageSize = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=100000)]
Owned = TypeVar("Owned", bound=Base)


async def owned(db: AsyncSession, model: type[Owned], resource_id: UUID, user: User, lock: bool = False) -> Owned:
    query = select(model).where(model.id == resource_id, model.user_id == user.id)
    item = await db.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise HTTPException(404, "Ресурс не найден")
    return item


def require_writable(user: User):
    if user.is_demo:
        raise HTTPException(403, "Демонстрационный аккаунт доступен только для чтения")
