from __future__ import annotations

import pytest

from app.models.user import User

@pytest.mark.anyio
async def test_user_status_methods_update_state() -> None:
    user = User(username="moluo", password_hash="hashed-password")

    await user.disable()
    assert user.disabled_at is not None
    assert user.is_disabled is True
    assert user.is_active is False

    await user.enable()
    assert user.disabled_at is None
    assert user.is_disabled is False
    assert user.is_active is True

    await user.update_last_login()
    assert user.last_login_at is not None