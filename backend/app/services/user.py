from __future__ import annotations

import io

from fastapi import UploadFile
from PIL import Image
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import oss_root_path, settings
from app.core.database import async_session_maker
from app.models.user import User
from app.schemas.user import (
    UserAvatarUpdate,
    UserCreate,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserUpdate,
)
from app.utils.string_tools import hash_password, verify_password
from app.utils.time_tools import utc_now


class UserServiceError(Exception):
    """用户服务层基础异常。"""


class UserNotFoundError(UserServiceError):
    """用户不存在异常。"""


class UserNameConflictError(UserServiceError):
    """用户名冲突异常。"""


class UserEmailConflictError(UserServiceError):
    """用户邮箱冲突异常。"""


class UserPasswordMismatchError(UserServiceError):
    """当前密码校验失败异常。"""


class UserAvatarInvalidError(UserServiceError):
    """头像文件格式或内容不合法异常。"""


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """按用户名查询单个用户。"""
    statement = select(User).where(User.username == username)
    result = await session.exec(statement)
    return result.first()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """按邮箱查询单个用户。"""
    statement = select(User).where(User.email == email)
    result = await session.exec(statement)
    return result.first()


async def get_user_by_public_id(session: AsyncSession, public_id: str) -> User | None:
    """按公开 ID 查询单个用户。"""
    statement = select(User).where(User.public_id == public_id)
    result = await session.exec(statement)
    return result.first()


async def get_user_or_raise(session: AsyncSession, public_id: str) -> User:
    """按公开 ID 获取用户，不存在时抛出业务异常。"""
    user = await get_user_by_public_id(session, public_id)
    if user is None:
        raise UserNotFoundError("User not found")
    return user


async def ensure_unique_username(
    session: AsyncSession,
    username: str,
    current_user_id: int | None = None,
) -> None:
    """校验用户名在当前系统内唯一。"""
    existing_user = await get_user_by_username(session, username)
    if existing_user is None:
        return
    if current_user_id is not None and existing_user.id == current_user_id:
        return
    raise UserNameConflictError("Username already exists")


async def ensure_unique_email(
    session: AsyncSession,
    email: str | None,
    current_user_id: int | None = None,
) -> None:
    """校验非空邮箱在当前系统内唯一。"""
    if email is None:
        return

    existing_user = await get_user_by_email(session, email)
    if existing_user is None:
        return
    if current_user_id is not None and existing_user.id == current_user_id:
        return
    raise UserEmailConflictError("Email already exists")


async def list_users(session: AsyncSession) -> list[User]:
    """获取用户列表。"""
    statement = select(User).order_by(User.sort_order, User.id)
    result = await session.exec(statement)
    return list(result.all())


async def create_user(session: AsyncSession, payload: UserCreate) -> User:
    """创建用户。"""
    await ensure_unique_username(session, payload.username)
    await ensure_unique_email(session, payload.email)

    now = utc_now()
    user = User(
        username=payload.username,
        nickname=payload.nickname,
        email=payload.email,
        avatar_url=payload.avatar_url,
        password_hash=hash_password(payload.password),
        sort_order=payload.sort_order,
        is_superuser=payload.is_superuser,
        disabled_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, public_id: str, payload: UserUpdate) -> User:
    """更新用户信息。"""
    user = await get_user_or_raise(session, public_id)
    fields_set = payload.model_fields_set

    if "username" in fields_set and payload.username is not None:
        await ensure_unique_username(session, payload.username, current_user_id=user.id)
        user.username = payload.username
    if "email" in fields_set:
        await ensure_unique_email(session, payload.email, current_user_id=user.id)
        user.email = payload.email
    if "nickname" in fields_set:
        user.nickname = payload.nickname
    if "avatar_url" in fields_set:
        user.avatar_url = payload.avatar_url
    if "password" in fields_set and payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if "sort_order" in fields_set and payload.sort_order is not None:
        user.sort_order = payload.sort_order
    if "is_superuser" in fields_set and payload.is_superuser is not None:
        user.is_superuser = payload.is_superuser
    if "disabled_at" in fields_set:
        user.disabled_at = payload.disabled_at

    user.updated_at = utc_now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_current_user(session: AsyncSession, current_user_public_id: str) -> User:
    """获取当前登录用户。"""
    return await get_user_or_raise(session, current_user_public_id)


async def update_current_user_profile(
    session: AsyncSession,
    current_user_public_id: str,
    payload: UserProfileUpdate,
) -> User:
    """更新当前登录用户基础资料。"""
    user = await get_user_or_raise(session, current_user_public_id)
    fields_set = payload.model_fields_set

    if "username" in fields_set and payload.username is not None:
        await ensure_unique_username(session, payload.username, current_user_id=user.id)
        user.username = payload.username
    if "email" in fields_set:
        await ensure_unique_email(session, payload.email, current_user_id=user.id)
        user.email = payload.email
    if "nickname" in fields_set:
        user.nickname = payload.nickname

    user.updated_at = utc_now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_current_user_password(
    session: AsyncSession,
    current_user_public_id: str,
    payload: UserPasswordUpdate,
) -> User:
    """校验当前密码后更新当前登录用户密码。"""
    user = await get_user_or_raise(session, current_user_public_id)
    if not verify_password(payload.old_password, user.password_hash):
        raise UserPasswordMismatchError("Current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    user.updated_at = utc_now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_current_user_avatar(
    session: AsyncSession,
    current_user_public_id: str,
    payload: UserAvatarUpdate,
) -> User:
    """更新当前登录用户头像地址。"""
    user = await get_user_or_raise(session, current_user_public_id)
    user.avatar_url = payload.avatar_url
    user.updated_at = utc_now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


_ALLOWED_AVATAR_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg"}
_AVATAR_OUTPUT_SIZE = 256
_AVATAR_MAX_BYTES = 5 * 1024 * 1024


async def upload_current_user_avatar(
    session: AsyncSession,
    current_user_public_id: str,
    upload: UploadFile,
) -> User:
    """接收用户上传的图片，中心裁剪为 1:1 后落盘并写回 avatar_url。"""
    if upload.content_type not in _ALLOWED_AVATAR_CONTENT_TYPES:
        raise UserAvatarInvalidError("仅支持 PNG/JPEG/JPG 格式的图片")

    data = await upload.read()
    if not data:
        raise UserAvatarInvalidError("图片内容为空")
    if len(data) > _AVATAR_MAX_BYTES:
        raise UserAvatarInvalidError("图片过大，最多支持 5MB")

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            cropped = image.crop((left, top, left + side, top + side))
            cropped = cropped.resize(
                (_AVATAR_OUTPUT_SIZE, _AVATAR_OUTPUT_SIZE),
                Image.Resampling.LANCZOS,
            )
            if cropped.mode in ("RGBA", "LA"):
                background = Image.new("RGB", cropped.size, (255, 255, 255))
                background.paste(cropped, mask=cropped.split()[-1])
                cropped = background
            elif cropped.mode != "RGB":
                cropped = cropped.convert("RGB")

            user = await get_user_or_raise(session, current_user_public_id)
            avatar_dir = oss_root_path() / "avatars"
            avatar_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(utc_now().timestamp())
            filename = f"{user.public_id}_{timestamp}.jpg"
            target_path = avatar_dir / filename
            cropped.save(target_path, format="JPEG", quality=88, optimize=True)
    except UserServiceError:
        raise
    except Exception as exc:
        raise UserAvatarInvalidError(f"图片解析失败：{exc}") from exc

    user.avatar_url = f"/oss/avatars/{filename}"
    user.updated_at = utc_now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def disable_user(session: AsyncSession, public_id: str) -> User:
    """禁用用户。"""
    user = await get_user_or_raise(session, public_id)
    await user.disable()
    user.updated_at = utc_now()
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, public_id: str) -> None:
    """删除用户。"""
    user = await get_user_or_raise(session, public_id)
    await session.delete(user)
    await session.commit()


async def ensure_default_admin() -> None:
    """确保数据库中存在默认管理员账号。"""
    async with async_session_maker() as session:
        result = await session.exec(select(User.id).where(User.is_superuser.is_(True)))
        existing_admin = result.first()
        if existing_admin is not None:
            return

        admin_user = await get_user_by_username(session, settings.user_default_admin_name)
        if admin_user is not None:
            admin_user.is_superuser = True
            admin_user.updated_at = utc_now()
            session.add(admin_user)
            await session.commit()
            return

        now = utc_now()
        admin_user = User(
            username=settings.user_default_admin_name,
            nickname=settings.user_default_admin_name,
            password_hash=hash_password(settings.user_default_admin_password),
            sort_order=0,
            is_superuser=True,
            disabled_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(admin_user)
        await session.commit()
