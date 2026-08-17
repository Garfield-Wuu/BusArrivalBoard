"""
车来了 SDK 异常定义
"""

from __future__ import annotations


class ChelaiLeException(Exception):
    """车来了 SDK 基础异常"""

    pass


class APIError(ChelaiLeException):
    """API 请求错误"""

    def __init__(self, message: str, status_code: int | None = None, response: str | None = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(message)

    def __str__(self):
        if self.status_code:
            return f"API Error [{self.status_code}]: {self.message}"
        return f"API Error: {self.message}"


class DecryptionError(ChelaiLeException):
    """数据解密失败"""

    pass


class NetworkError(ChelaiLeException):
    """网络请求失败"""

    pass


class ValidationError(ChelaiLeException):
    """数据验证失败"""

    pass


class CityNotFoundError(ChelaiLeException):
    """城市未找到"""

    pass


class LineNotFoundError(ChelaiLeException):
    """线路未找到"""

    pass


class StationNotFoundError(ChelaiLeException):
    """站点未找到"""

    pass
