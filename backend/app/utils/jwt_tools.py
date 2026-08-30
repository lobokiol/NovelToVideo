"""
JWT官网：https://www.jwt.io/
"""
from __future__ import annotations

from datetime import timedelta
import json
from uuid import uuid4

import jwt

from app.core.config import settings
from app.utils.time_tools import utc_now

def _token_cache_key(jti: str) -> str:
    """生成 token 在 Redis 中的缓存键。

    Args:
        jti: JWT 的唯一标识。

    Returns:
        str: Redis 中用于缓存 token 的键名。
    """
    return f"{settings.redis_token_key_prefix}{jti}"


async def cache_token(jti: str, public_id: str, token_type: str, expires_at: int) -> None:
    """缓存 token 标识，用于后续校验和登出吊销。

    Args:
        jti: JWT 的唯一标识。
        public_id: 用户对外唯一标识。
        token_type: token 类型，例如 access 或 refresh。
        expires_at: token 过期时间戳。
    """
    from app.core.database import redis_client

    ttl_seconds = expires_at - int(utc_now().timestamp())
    if ttl_seconds <= 0:
        return

    value = json.dumps(
        {
            "public_id": public_id,
            "token_type": token_type,
            "expires_at": expires_at,
        },
        separators=(",", ":"),
    )

    await redis_client.set(_token_cache_key(jti), value, ex=ttl_seconds)



async def _create_token(public_id: str, username: str, token_type: str, expires_seconds: int) -> tuple[str, str, int]:
    """创建 JWT，并返回 token 信息。

    Args:
        public_id: 用户对外唯一标识。
        username: 用户名。
        token_type: token 类型，例如 access 或 refresh。
        expires_seconds: token 过期秒数。

    Returns:
        tuple[str, str, int]: token 字符串、jti 和过期秒数。
    """
    now = utc_now()
    expire = now + timedelta(seconds=expires_seconds)
    jti = uuid4().hex

    payload = {
        "sub": public_id,
        "username": username,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    await cache_token(jti, public_id, token_type, int(expire.timestamp()))
    return token, jti, expires_seconds


async def create_login_tokens(public_id: str, username: str) -> dict[str, str | int]:
    """生成登录所需的 access token 和 refresh token。

    Args:
        public_id: 用户对外唯一标识。
        username: 用户名。

    Returns:
        dict[str, str | int]: 登录 token 响应数据。
    """
    access_token, _, expires_in = await _create_token(
        public_id=public_id,
        username=username,
        token_type="access",
        expires_seconds=settings.access_token_expire_seconds,
    )
    refresh_token, _, _ = await _create_token(
        public_id=public_id,
        username=username,
        token_type="refresh",
        expires_seconds=settings.refresh_token_expire_seconds,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
    }


async def decode_token(token: str, *, refresh_access_ttl: bool = False) -> dict[str, str | int]:
    """解析并校验 JWT。

    Args:
        token: 待解析的 JWT 字符串。

    Returns:
        dict[str, str | int]: 解析后的 token 载荷。
    """
    from app.core.database import redis_client

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    jti = str(payload.get("jti", ""))
    cache_key = _token_cache_key(jti)

    if not jti or await redis_client.get(cache_key) is None:
        raise ValueError("Token has been revoked")

    if refresh_access_ttl and payload.get("type") == "access":
        await redis_client.expire(cache_key, settings.access_token_expire_seconds)

    return payload


async def create_access_token_from_refresh_token(refresh_token: str) -> dict[str, str | int]:
    """根据 refresh token 生成新的 access token。

    Args:
        refresh_token: 用于刷新 access token 的 refresh token。

    Returns:
        dict[str, str | int]: 新的 access token 响应数据。
    """
    payload = await decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("Refresh token required")

    public_id = str(payload.get("sub", ""))
    username = str(payload.get("username", ""))
    if not public_id or not username:
        raise ValueError("Invalid refresh token payload")

    access_token, _, expires_in = await _create_token(
        public_id=public_id,
        username=username,
        token_type="access",
        expires_seconds=settings.access_token_expire_seconds,
    )
    return {
        "access_token": access_token,
        "expires_in": expires_in,
    }


async def revoke_token(jti: str) -> None:
    """登出时吊销 token。

    Args:
        jti: JWT 的唯一标识。
    """
    from app.core.database import redis_client

    await redis_client.delete(_token_cache_key(jti))
