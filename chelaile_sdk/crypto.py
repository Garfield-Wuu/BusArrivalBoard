"""
车来了 SDK - 核心加密与签名模块

提供 MD5 签名和 AES-256-ECB 解密功能
"""

import base64
import hashlib

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 车来了 API 常量
SIGN_SALT = "qwihrnbtmj"
AES_KEY = b"FF32AE65FBFD19414EAAFF6291A54B42"  # 32-byte UTF-8 key


def generate_signature(params: dict[str, str]) -> str:
    """
    生成车来了 API 签名

    算法: MD5('"key1"="value1"&"key2"="value2"&...&salt')

    Args:
        params: 请求参数字典

    Returns:
        32位小写MD5签名

    Example:
        >>> generate_signature({"cityId": "014", "key": "M592"})
        'a1b2c3d4...'
    """
    # 拼接格式: "key1"="value1"&"key2"="value2"&salt
    parts = [f'"{key}"="{value}"' for key, value in params.items()]
    sign_string = "&".join(parts) + SIGN_SALT

    return hashlib.md5(sign_string.encode()).hexdigest()


def decrypt_aes_ecb(ciphertext: str) -> str:
    """
    AES-256-ECB 解密车来了响应数据

    Args:
        ciphertext: Base64 编码的密文

    Returns:
        解密后的明文字符串

    Raises:
        ValueError: 解密失败或填充错误

    Example:
        >>> decrypt_aes_ecb("encrypted_base64_string")
        '{"result": {...}}'
    """
    try:
        # Base64 解码
        encrypted_data = base64.b64decode(ciphertext)

        # 创建 AES-256-ECB 解密器
        cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB(), backend=default_backend())
        decryptor = cipher.decryptor()

        # 解密
        decrypted_padded = decryptor.update(encrypted_data) + decryptor.finalize()

        # PKCS7 去填充
        padding_length = decrypted_padded[-1]
        if padding_length > 16 or padding_length < 1:
            raise ValueError(f"Invalid padding length: {padding_length}")

        decrypted = decrypted_padded[:-padding_length]

        return decrypted.decode("utf-8")

    except Exception as e:
        raise ValueError(f"AES decryption failed: {e}") from e


def verify_signature(params: dict[str, str], signature: str) -> bool:
    """
    验证签名是否正确（用于测试）

    Args:
        params: 参数字典
        signature: 待验证的签名

    Returns:
        签名是否匹配
    """
    expected = generate_signature(params)
    return expected == signature
