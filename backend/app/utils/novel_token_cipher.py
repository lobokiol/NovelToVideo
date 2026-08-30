"""笔趣阁家族的小说来源 API token 的可逆加解密工具。"""

from __future__ import annotations

import base64
import hashlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

# apibi.cc 家族派生密钥所用的固定种子明文。
APIBI_TOKEN_SEED = "book@token.html"

_AES_BLOCK_BITS = 128


class AesMd5TokenCipher:
    """基于固定种子 MD5 派生密钥的 AES-128-CBC token 加解密器。

    适用于密钥与 IV 均来自 ``md5(seed)`` 十六进制串的站点：前 16 位作 IV，
    后 16 位作 KEY，明文经 PKCS7 填充后 AES-CBC 加密并 base64 输出。
    """

    def __init__(self, seed: str) -> None:
        self._seed = seed

    def _derive_key_iv(self) -> tuple[bytes, bytes]:
        """由种子明文派生 (key, iv) 字节对。"""
        code = hashlib.md5(self._seed.encode("utf-8")).hexdigest()
        iv = code[:16].encode("utf-8")
        key = code[16:].encode("utf-8")
        return key, iv

    def encrypt(self, plaintext: str) -> str:
        """加密明文并返回 base64 字符串。"""
        key, iv = self._derive_key_iv()
        padder = PKCS7(_AES_BLOCK_BITS).padder()
        padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
        encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(ciphertext).decode("ascii")

    def decrypt(self, token: str) -> str:
        """解密 base64 token 并返回明文，便于调试与校验。"""
        key, iv = self._derive_key_iv()
        raw = base64.b64decode(token)
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(raw) + decryptor.finalize()
        unpadder = PKCS7(_AES_BLOCK_BITS).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


# 已支持的 token 加密算法注册表，键为来源配置中引用的算法名。
TOKEN_CIPHERS: dict[str, AesMd5TokenCipher] = {
    "apibi": AesMd5TokenCipher(APIBI_TOKEN_SEED),
}


def encrypt_token(cipher_name: str, plaintext: str) -> str:
    """按算法名加密明文 token。

    Args:
        cipher_name: 注册表中的算法名，如 ``apibi``。
        plaintext: 待加密明文，通常为 JSON 字符串。

    Raises:
        KeyError: 算法名未注册时抛出。

    Returns:
        base64 编码的 token 字符串。
    """
    cipher = TOKEN_CIPHERS.get(cipher_name)
    if cipher is None:
        raise KeyError(f"unknown token cipher: {cipher_name}")
    return cipher.encrypt(plaintext)


def decrypt_token(cipher_name: str, token: str) -> str:
    """按算法名解密 token，返回明文。"""
    cipher = TOKEN_CIPHERS.get(cipher_name)
    if cipher is None:
        raise KeyError(f"unknown token cipher: {cipher_name}")
    return cipher.decrypt(token)


if __name__ == "__main__":
    """演示 apibi.cc token 的加密与解密闭环。"""
    samples = [
        '{"id":"2530"}',
        '{"id":2530,"chapterid":5}',
    ]
    for plaintext in samples:
        token = encrypt_token("apibi", plaintext)
        restored = decrypt_token("apibi", token)
        print(f"明文: {plaintext}")
        print(f"token: {token}")
        print(f"还原: {restored}")
        print(f"校验: {restored == plaintext}")
        print("-" * 40)
