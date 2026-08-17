"""加密与签名模块测试（纯离线，不触网）"""
import base64

import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from chelaile_sdk.crypto import (
    AES_KEY,
    SIGN_SALT,
    decrypt_aes_ecb,
    generate_signature,
    verify_signature,
)


def _encrypt(plaintext: str) -> str:
    """测试辅助：用同一密钥做 AES-256-ECB + PKCS7 加密"""
    data = plaintext.encode("utf-8")
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    encryptor = Cipher(
        algorithms.AES(AES_KEY), modes.ECB(), backend=default_backend()
    ).encryptor()
    return base64.b64encode(encryptor.update(data) + encryptor.finalize()).decode()


class TestGenerateSignature:
    def test_returns_32_char_lowercase_md5(self):
        sig = generate_signature({"cityId": "014", "key": "M592"})
        assert len(sig) == 32
        assert sig == sig.lower()
        assert all(c in "0123456789abcdef" for c in sig)

    def test_is_deterministic(self):
        params = {"cityId": "014", "lineId": "0755182470300"}
        assert generate_signature(params) == generate_signature(params)

    def test_param_order_matters(self):
        """签名按插入顺序拼接，顺序不同结果必须不同"""
        a = generate_signature({"a": "1", "b": "2"})
        b = generate_signature({"b": "2", "a": "1"})
        assert a != b

    def test_value_change_changes_signature(self):
        a = generate_signature({"cityId": "014"})
        b = generate_signature({"cityId": "034"})
        assert a != b

    def test_matches_reference_algorithm(self):
        """锁定拼接格式: '"k"="v"&"k2"="v2"' + SALT"""
        import hashlib

        params = {"cityId": "014", "key": "M592"}
        expected = hashlib.md5(
            ('"cityId"="014"&"key"="M592"' + SIGN_SALT).encode()
        ).hexdigest()
        assert generate_signature(params) == expected

    def test_empty_params(self):
        import hashlib

        assert generate_signature({}) == hashlib.md5(SIGN_SALT.encode()).hexdigest()


class TestVerifySignature:
    def test_accepts_valid_signature(self):
        params = {"cityId": "014"}
        assert verify_signature(params, generate_signature(params)) is True

    def test_rejects_invalid_signature(self):
        assert verify_signature({"cityId": "014"}, "0" * 32) is False


class TestDecryptAesEcb:
    def test_roundtrip_ascii(self):
        plaintext = '{"status":"00"}'
        assert decrypt_aes_ecb(_encrypt(plaintext)) == plaintext

    def test_roundtrip_chinese(self):
        plaintext = '{"sn":"安翼嘉寓","line":"M592"}'
        assert decrypt_aes_ecb(_encrypt(plaintext)) == plaintext

    def test_roundtrip_exact_block_multiple(self):
        """长度正好为 16 字节倍数时，PKCS7 会补满一整块"""
        plaintext = "A" * 32
        assert decrypt_aes_ecb(_encrypt(plaintext)) == plaintext

    def test_key_is_32_bytes(self):
        """AES-256 要求 32 字节密钥；必须是 utf8 字面量而非 hex 解码"""
        assert len(AES_KEY) == 32

    def test_invalid_base64_raises(self):
        with pytest.raises(ValueError):
            decrypt_aes_ecb("!!!not-base64!!!")

    def test_wrong_length_ciphertext_raises(self):
        with pytest.raises(ValueError):
            decrypt_aes_ecb(base64.b64encode(b"short").decode())
