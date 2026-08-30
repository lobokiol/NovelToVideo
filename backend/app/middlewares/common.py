from __future__ import annotations

from collections.abc import AsyncGenerator
from time import perf_counter
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.utils.jwt_tools import decode_token

BEARER_AUTH_HEADER = {"WWW-Authenticate": "Bearer"}
http_bearer = HTTPBearer(auto_error=False)

async def request_duration_middleware(request: Request) -> AsyncGenerator[None, None]:
    """记录当前请求的处理耗时。

    Args:
        request: 当前 FastAPI 请求对象。

    Yields:
        None: 交还控制权给后续依赖和路由处理函数。
    """
    start_time = perf_counter()
    try:
        yield  # 此处不再执行当前中间件，进入下一个中间件或者视图
    finally:
        duration_ms = round((perf_counter() - start_time) * 1000, 3)
        request.state.request_duration_ms = duration_ms
        print(
            f"Request {request.method} {request.url.path} completed in {duration_ms:.3f} ms",
            flush=True,
        )


async def jwt_auth_middleware(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(http_bearer)],
) -> None:
    """校验当前请求携带的 access token。

    Args:
        request: 当前 FastAPI 请求对象。

    Raises:
        HTTPException: 未提供 token、token 无效或 token 类型不是 access 时抛出。
    """
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供 access token",
            headers=BEARER_AUTH_HEADER,
        )

    try:
        payload = await decode_token(credentials.credentials, refresh_access_ttl=True)
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="access token 无效或已过期",
            headers=BEARER_AUTH_HEADER,
        ) from exc

    if payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供 access token",
            headers=BEARER_AUTH_HEADER,
        )

    request.state.current_user_public_id = str(payload["sub"])
    request.state.current_token_payload = payload
