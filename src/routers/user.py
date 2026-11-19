from fastapi import APIRouter
from fastapi import Depends, HTTPException, status
from src.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession

from src.dependencies import get_current_user
from src.models import UsersOrm
from src.queries.orm import UsersRepository, verify_password, RefreshTokensRepository, hash_password
from src.schemas import UserRead, UserCreate, LoginRequest, Token, RefreshRequest, UserUpdate, PasswordChange
from src.security import create_access_token, hash_token

router = APIRouter(tags=["user_&_auth"])

@router.post("/users", response_model=UserRead)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    email = payload.email.lower()
    existing = await UsersRepository.get_by_email(session, email)

    if existing is None:
        user = await UsersRepository.create(session, email=email, password=payload.password)
        if user is not None:
            return user

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await UsersRepository.get_by_email(session, payload.email.lower())
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(user.id)
    refresh_token = await RefreshTokensRepository.create(session, user.id)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_session)):
    stored = await RefreshTokensRepository.get_valid(session, hash_token(payload.refresh_token))
    if stored is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = stored.user_id
    await RefreshTokensRepository.revoke(session, stored)
    new_access = create_access_token(user_id)
    new_refresh = await RefreshTokensRepository.create(session, user_id)
    return Token(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(payload: RefreshRequest, session: AsyncSession = Depends(get_session)):
    stored = await RefreshTokensRepository.get_valid(session, hash_token(payload.refresh_token))
    if stored is not None:
        await RefreshTokensRepository.revoke(session, stored)


@router.get("/users/me", response_model=UserRead)
async def read_me(current_user: UsersOrm = Depends(get_current_user)):
    return current_user


@router.patch("/users/me", response_model=UserRead)
async def update_me(payload: UserUpdate, current_user: UsersOrm = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session),):

    return await UsersRepository.update(session, current_user, payload.model_dump(exclude_unset=True))


@router.post("/users/me/password", status_code=204)
async def change_passwd(payload: PasswordChange, current_user: UsersOrm = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid current password")
    await UsersRepository.update(session, current_user, {"password_hash": hash_password(payload.new_password)})
    await RefreshTokensRepository.revoke_all(session, current_user.id)


@router.post("/logout-all", status_code=204)
async def logout_all(current_user: UsersOrm = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await RefreshTokensRepository.revoke_all(session, current_user.id)