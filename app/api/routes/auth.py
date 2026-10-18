from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import SessionDep
from app.core.security import create_access_token
from app.schemas.user import Token, UserCreate, UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, session: SessionDep) -> UserRead:
    user = await auth_service.register_user(session, data)
    return UserRead.model_validate(user)


# OAuth2 password form (the email goes in `username`), so the "Authorize" button in /docs works.
@router.post("/login")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    user = await auth_service.authenticate_user(session, form.username, form.password)
    return Token(access_token=create_access_token(user.id))
