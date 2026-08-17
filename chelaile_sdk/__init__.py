"""
车来了 SDK - 核心模块导出

Example:
    >>> from chelaile_sdk import ChelaiLeClient
    >>> client = ChelaiLeClient()
    >>> cities = client.get_city_list()
"""

__version__ = "0.1.0"
__author__ = "Garfield Wu"

# 核心类导出
from .client import ChelaiLeClient
from .models import (
    City,
    LineInfo,
    Station,
    BusInfo,
    BusETA,
    RealtimeResult,
)
from .exceptions import (
    ChelaiLeException,
    APIError,
    NetworkError,
    DecryptionError,
    ValidationError,
    CityNotFoundError,
    LineNotFoundError,
    StationNotFoundError,
)

__all__ = [
    # Client
    "ChelaiLeClient",
    # Models
    "City",
    "LineInfo",
    "Station",
    "BusInfo",
    "BusETA",
    "RealtimeResult",
    # Exceptions
    "ChelaiLeException",
    "APIError",
    "NetworkError",
    "DecryptionError",
    "ValidationError",
    "CityNotFoundError",
    "LineNotFoundError",
    "StationNotFoundError",
]
