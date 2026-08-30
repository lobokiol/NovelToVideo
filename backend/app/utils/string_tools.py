from __future__ import annotations

from hashlib import sha256
import bcrypt
BCRYPT_SHA256_PREFIX = "$bcrypt-sha256$"

def build_database_url(
    *,
    db_engine: str,
    db_driver: str,
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str,
    db_sqlite_path: str,
) -> str:
    """拼接数据库连接URL字符串。

    Args:
        db_engine: 数据库引擎类型。
        db_driver: 数据库驱动名称。
        db_host: 数据库主机地址。
        db_port: 数据库端口。
        db_name: 数据库名称。
        db_user: 数据库用户名。
        db_password: 数据库密码。
        db_sqlite_path: SQLite 数据文件路径。

    Returns:
        str: 可用于 SQLModel 的数据库连接 URL。
    """
    if db_engine.lower() == "sqlite":
        return f"{db_engine}+{db_driver}:///{db_sqlite_path}"

    return f"{db_engine.lower()}+{db_driver}://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


def _normalize_password(password: str) -> bytes:
    """将明文密码归一化为适合 bcrypt 处理的固定长度字节串。"""
    return sha256(password.encode("utf-8")).hexdigest().encode("ascii")

def hash_password(password: str) -> str:
    """生成密码哈希。

    Args:
        password: 待处理的明文密码。

    Returns:
        str: 带算法前缀的 bcrypt 密码哈希。
    """
    password_hash = bcrypt.hashpw(_normalize_password(password), bcrypt.gensalt())
    return f"{BCRYPT_SHA256_PREFIX}{password_hash.decode('ascii')}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文密码与密码哈希是否匹配。

    Args:
        plain_password: 用户的明文密码。
        password_hash: 存档的密码哈希。

    Returns:
        bool: 校验结果。
    """
    try:
        if password_hash.startswith(BCRYPT_SHA256_PREFIX):
            stored_hash = password_hash.removeprefix(BCRYPT_SHA256_PREFIX).encode("ascii")
            return bcrypt.checkpw(_normalize_password(plain_password), stored_hash)

        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False
