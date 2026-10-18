from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotAuthenticated, PermissionDenied
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User, UserRole

# auto_error=False: we raise our own NotAuthenticated so the error uses the project's error shape.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_optional_user(
    session: SessionDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> User | None:
    # No token means an anonymous visitor; a bad token is still an error.
    if token is None:
        return None
    user = await session.get(User, decode_access_token(token))
    if user is None or not user.is_active:
        raise NotAuthenticated()
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise NotAuthenticated()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole):
    async def check_role(user: CurrentUser) -> User:
        # Admins can do everything (PLAN.md §3).
        if user.role != UserRole.admin and user.role not in roles:
            raise PermissionDenied()
        return user

    return check_role


OrganizerUser = Annotated[User, Depends(require_role(UserRole.organizer))]
CustomerUser = Annotated[User, Depends(require_role(UserRole.customer))]
