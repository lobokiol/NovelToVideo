"""Provider 敏感输入值的可逆加解密工具。"""

from __future__ import annotations

import base64
from collections.abc import Iterator
import hashlib
import hmac
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from app.core.config import settings

ENCRYPTED_VALUE_PREFIX = "enc:v1:"
_NONCE_SIZE = 16
_TAG_SIZE = 16


def is_encrypted_value(value: object) -> bool:
    """判断传入值是否为当前工具生成的加密字符串。"""
    return isinstance(value, str) and value.startswith(ENCRYPTED_VALUE_PREFIX)


def encrypt_secret(value: object, *, secret_key: str | None = None) -> str:
    """加密敏感值，空值和已加密值会原样返回。

    Args:
        value: 待加密的明文值，非字符串会先转换为字符串。
        secret_key: 可选的加密盐值；默认使用项目配置中的 secret_key。

    Returns:
        带有固定前缀的加密字符串。
    """
    plaintext = "" if value is None else str(value)
    if not plaintext or is_encrypted_value(plaintext):
        return plaintext

    key = _secret_key_bytes(secret_key)
    nonce = os.urandom(_NONCE_SIZE)
    cipher = _xor_bytes(plaintext.encode("utf-8"), _key_stream(key, nonce))
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()[:_TAG_SIZE]
    token = base64.urlsafe_b64encode(nonce + tag + cipher).decode("ascii")
    return f"{ENCRYPTED_VALUE_PREFIX}{token}"


def decrypt_secret(value: object, *, secret_key: str | None = None) -> str:
    """解密敏感值，非加密值会原样返回。

    Args:
        value: 待解密的密文值，非字符串会先转换为字符串。
        secret_key: 可选的解密盐值；默认使用项目配置中的 secret_key。

    Raises:
        ValueError: 密文格式、长度或校验不合法时抛出。

    Returns:
        解密后的明文字符串。
    """
    ciphertext = "" if value is None else str(value)
    if not ciphertext or not is_encrypted_value(ciphertext):
        return ciphertext

    key = _secret_key_bytes(secret_key)
    payload = ciphertext[len(ENCRYPTED_VALUE_PREFIX) :]
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    except Exception as exc:
        raise ValueError("密钥密文格式不合法") from exc

    min_size = _NONCE_SIZE + _TAG_SIZE
    if len(raw) <= min_size:
        raise ValueError("密钥密文长度不合法")

    nonce = raw[:_NONCE_SIZE]
    tag = raw[_NONCE_SIZE:min_size]
    cipher = raw[min_size:]
    expected_tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()[:_TAG_SIZE]
    if not hmac.compare_digest(tag, expected_tag):
        raise ValueError("密钥密文校验失败")

    plaintext = _xor_bytes(cipher, _key_stream(key, nonce))
    return plaintext.decode("utf-8")


def _secret_key_bytes(secret_key: str | None = None) -> bytes:
    """将配置中的 secret_key 派生为固定长度字节密钥。"""
    raw_key = secret_key if secret_key is not None else settings.secret_key
    return hashlib.sha256(str(raw_key).encode("utf-8")).digest()


def _key_stream(key: bytes, nonce: bytes) -> Iterator[int]:
    """基于 HMAC-SHA256 生成可重复的异或字节流。"""
    counter = 0
    while True:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
        yield from block


def _xor_bytes(data: bytes, stream: Iterator[int]) -> bytes:
    """使用给定字节流对数据执行异或变换。"""
    return bytes(item ^ next(stream) for item in data)


if __name__ == "__main__":
    """演示密码字符串的加密和解密流程。"""
    password = "demo-password-123"
    encrypted = encrypt_secret(password)
    decrypted = decrypt_secret(encrypted)

    print(f"原始密码: {password}")
    print(f"加密结果: {encrypted}")
    print(f"解密结果: {decrypted}")
    print(f"解密校验: {decrypted == password}")
