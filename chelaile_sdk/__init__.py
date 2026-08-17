"""
车来了 SDK - Python 封装

提供城市查询、线路搜索、站点列表、实时公交到站信息等功能。

Example:
    >>> from chelaile_sdk import ChelaiLeClient
    >>>
    >>> with ChelaiLeClient() as client:
    ...     # 查找城市
    ...     city = client.search_city("深圳")
    ...
    ...     # 搜索线路
    ...     lines = client.search_line(city.city_id, "M592")
    ...     line = lines[0]
    ...
    ...     # 获取站点列表
    ...     stations = client.get_line_detail(city.city_id, line.line_id)
    ...     target = next(s for s in stations if "安翼嘉寓" in s.name)
    ...
    ...     # 查询实时到站
    ...     result = client.get_realtime_buses(
    ...         city.city_id, line.line_id,
    ...         target.station_id, target.order,
    ...         target.lat, target.lng
    ...     )
    ...
    ...     # 最近的车还有几分钟到站
    ...     print(f"{result.nearest_bus.eta_minutes} 分钟")
"""

from .client import ChelaiLeClient
from .exceptions import (
    APIError,
    ChelaiLeException,
    CityNotFoundError,
    DecryptionError,
    LineNotFoundError,
    NetworkError,
    StationNotFoundError,
    ValidationError,
)
from .models import BusETA, BusInfo, City, LineInfo, RealtimeResult, Station

__version__ = "1.0.0"

__all__ = [
    "ChelaiLeClient",
    # Models
    "BusETA",
    "BusInfo",
    "City",
    "LineInfo",
    "RealtimeResult",
    "Station",
    # Exceptions
    "APIError",
    "ChelaiLeException",
    "CityNotFoundError",
    "DecryptionError",
    "LineNotFoundError",
    "NetworkError",
    "StationNotFoundError",
    "ValidationError",
]
