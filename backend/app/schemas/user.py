from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class UserBase(BaseModel):
    """用户基础资料。"""

    username: str = Field(min_length=3, max_length=64)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=512)
    sort_order: int = Field(default=0)
    is_superuser: bool = Field(default=False)


class UserCreate(UserBase):
    """创建用户请求模型。"""

    password: str = Field(min_length=6, max_length=128)
    repassword: str = Field(min_length=6, max_length=128)

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "UserCreate":
        if self.password != self.repassword:
            raise ValueError("两次输入的密码不一致")
        return self

class UserUpdate(BaseModel):
    """更新用户请求模型。"""

    username: str | None = Field(default=None, min_length=3, max_length=64)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=512)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    sort_order: int | None = None
    is_superuser: bool | None = None
    disabled_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    """当前登录用户资料更新请求模型。"""

    username: str | None = Field(default=None, min_length=3, max_length=64)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)


class UserPasswordUpdate(BaseModel):
    """当前登录用户密码更新请求模型。"""

    model_config = ConfigDict(populate_by_name=True)

    old_password: str = Field(
        min_length=6,
        max_length=128,
        validation_alias=AliasChoices("old_password", "oldPassword"),
    )
    new_password: str = Field(
        min_length=8,
        max_length=128,
        validation_alias=AliasChoices("new_password", "newPassword"),
    )
    confirm_password: str = Field(
        min_length=8,
        max_length=128,
        validation_alias=AliasChoices("confirm_password", "confirmPassword"),
    )

    @model_validator(mode="after")
    def validate_new_password(self) -> "UserPasswordUpdate":
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        if self.old_password == self.new_password:
            raise ValueError("新密码不能与当前密码相同")
        return self


class UserAvatarUpdate(BaseModel):
    """当前登录用户头像更新请求模型。"""

    model_config = ConfigDict(populate_by_name=True)

    avatar_url: str | None = Field(
        default=None,
        max_length=512,
        validation_alias=AliasChoices("avatar_url", "avatarUrl"),
    )


class UserRead(BaseModel):
    """用户响应模型。"""

    model_config = ConfigDict(from_attributes=True)

    public_id: str
    username: str
    nickname: str | None
    email: str | None
    avatar_url: str | None
    sort_order: int
    is_superuser: bool
    disabled_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserLogin(BaseModel):
    """用户登录请求。"""
    username: str = Field(min_length=1, max_length=50, description="用户名")
    password: str = Field(min_length=8, max_length=128, description="密码")


class LoginUserInfo(BaseModel):
    """登录成功后返回的用户详细信息。"""

    public_id: str
    username: str
    nickname: str | None = None


class UserLoginResponse(BaseModel):
    """用户登录响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: LoginUserInfo


class TokenRefreshRequest(BaseModel):
    """刷新 access token 的请求。"""

    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(
        min_length=1,
        validation_alias=AliasChoices("refresh_token", "refreshToken"),
    )


class TokenRefreshResponse(BaseModel):
    """刷新 access token 的响应。"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
