from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmailAlreadyRegistered, InvalidCredentials
from app.core.security import password_hash
from app.models.user import User
from app.schemas.user import UserCreate


async def register_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email.lower(),
        hashed_password=password_hash.hash(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    session.add(user)
    # Rely on the unique constraint instead of checking first: a check-then-insert
    # lets two simultaneous registrations with the same email both pass the check.
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise EmailAlreadyRegistered() from exc
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None or not user.is_active:
        raise InvalidCredentials()
    if not password_hash.verify(password, user.hashed_password):
        raise InvalidCredentials()
    return user
