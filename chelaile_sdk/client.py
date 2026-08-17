"""
车来了 API 客户端

封装签名、加密响应解析和数据模型转换，提供城市 / 线路 / 站点 / 实时到站查询能力。

Example:
    >>> client = ChelaiLeClient()
    >>> city = client.search_city("深圳")
    >>> lines = client.search_line(city.city_id, "M592")
    >>> stations = client.get_line_detail(city.city_id, lines[0].line_id)
    >>> target = next(s for s in stations if "安翼嘉寓" in s.name)
    >>> result = client.get_realtime_buses(
    ...     city.city_id, lines[0].line_id, target.station_id,
    ...     target.order, target.lat, target.lng,
    ... )
    >>> result.nearest_bus.eta_minutes
    3
"""
from __future__ import annotations

import json
from typing import Any, Optional

import requests

from .constants import (
    BASE_DOMAIN,
    BASE_URL,
    DEFAULT_PARAMS,
    DEFAULT_REFRESH_INTERVAL,
    ENDPOINTS,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
)
from .crypto import decrypt_aes_ecb, generate_signature
from .exceptions import (
    APIError,
    CityNotFoundError,
    DecryptionError,
    LineNotFoundError,
    NetworkError,
)
from .models import BusETA, BusInfo, City, LineInfo, RealtimeResult, Station

__all__ = ["ChelaiLeClient"]


def _extract_json(text: str) -> dict[str, Any]:
    """从车来了响应包装体中提取 JSON 对象。

    响应格式形如 ``**YGKJ{"jsonr": {...}}YGKJ##``，前后缀不固定，
    且 JSON 内部含有大量嵌套括号，因此必须做大括号配对扫描，
    不能简单地取 ``find('{')`` 到 ``rfind('}')``。

    Args:
        text: 原始响应文本。

    Returns:
        解析后的顶层 JSON 字典。

    Raises:
        APIError: 未找到合法的 JSON 边界或 JSON 解析失败。
    """
    start = text.find("{")
    if start == -1:
        raise APIError(f"响应中未找到 JSON 起始符: {text[:120]!r}")

    depth = 0
    end = -1
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise APIError("响应 JSON 大括号未闭合，可能被截断")

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise APIError(f"响应 JSON 解析失败: {exc}") from exc


def _as_float(value: Any, default: float = 0.0) -> float:
    """宽松地把 API 字段转成 float。"""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    """宽松地把 API 字段转成 int。"""
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


class ChelaiLeClient:
    """车来了公交数据 API 客户端。

    线程不安全（复用同一个 ``requests.Session``），如需并发请为每个线程创建独立实例。

    Attributes:
        timeout: 单次请求超时秒数。
        session: 底层 HTTP 会话对象。
    """

    def __init__(
        self,
        timeout: int = REQUEST_TIMEOUT,
        session: Optional[requests.Session] = None,
    ) -> None:
        """初始化客户端。

        Args:
            timeout: 请求超时秒数，默认取 ``constants.REQUEST_TIMEOUT``。
            session: 可选的外部 ``requests.Session``（便于注入代理 / 重试适配器）。
                传入时不会被 ``close()`` 关闭连接池以外的资源。
        """
        self.timeout = timeout
        self._owns_session = session is None
        self.session = session or requests.Session()
        self.session.headers.update(REQUEST_HEADERS)

    # ------------------------------------------------------------------ #
    # 底层请求
    # ------------------------------------------------------------------ #
    def _request(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
        *,
        signed: bool = True,
        base: str = BASE_URL,
    ) -> dict[str, Any]:
        """发送签名请求并返回解密后的 data 字典。

        流程：合并默认参数 -> 生成 ``cryptoSign`` -> GET -> 大括号配对提取 JSON
        -> 校验 ``status`` -> 若存在 ``encryptResult`` 则 AES-256-ECB 解密。

        Args:
            endpoint: 端点路径，如 ``/bus/query!nSearch.action``。
            params: 业务参数，会与 ``DEFAULT_PARAMS`` 合并（业务参数优先）。
            signed: 是否附加 ``cryptoSign`` 签名。城市列表等端点也接受签名，
                置为 False 可跳过。
            base: 基础 URL，默认 ``BASE_URL``；无 ``/api`` 前缀的端点传 ``BASE_DOMAIN``。

        Returns:
            业务数据字典（已解密）。

        Raises:
            NetworkError: 连接失败、超时或 HTTP 状态码异常。
            APIError: 响应结构异常或 ``status`` 非 ``"00"``。
            DecryptionError: ``encryptResult`` 解密或二次 JSON 解析失败。
        """
        merged: dict[str, str] = {
            **DEFAULT_PARAMS,
            **{k: ("" if v is None else str(v)) for k, v in (params or {}).items()},
        }
        if signed:
            merged["cryptoSign"] = generate_signature(merged)

        url = f"{base.rstrip('/')}/{endpoint.lstrip('/')}"

        try:
            response = self.session.get(url, params=merged, timeout=self.timeout)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise NetworkError(f"HTTP {status} 请求失败: {url}") from exc
        except requests.RequestException as exc:
            raise NetworkError(f"网络请求失败: {exc}") from exc

        payload = _extract_json(response.text)

        # 两种信封格式：
        #   1. 加密业务端点: {"jsonr": {"status": "00", "data": {...}}}
        #   2. 静态数据端点(城市列表): {"status": "OK", "data": {...}}
        envelope = payload.get("jsonr")
        if not isinstance(envelope, dict):
            # 无 jsonr 包装层，城市列表等端点用
            if "data" not in payload or "status" not in payload:
                raise APIError(f"无法识别的响应结构: {str(payload)[:120]}")
            envelope = payload

        status = str(envelope.get("status", "00"))
        if status not in ("00", "OK", "ok"):
            raise APIError(
                envelope.get("errmsg") or envelope.get("msg") or "API 返回错误状态",
                status_code=status,
            )

        data = envelope.get("data")
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise APIError(f"data 字段类型异常: {type(data).__name__}")

        encrypted = data.get("encryptResult")
        if encrypted:
            try:
                return json.loads(decrypt_aes_ecb(encrypted))
            except (ValueError, json.JSONDecodeError) as exc:
                raise DecryptionError(f"加密数据解析失败: {exc}") from exc

        return data

    def close(self) -> None:
        """关闭内部创建的 HTTP 会话（外部传入的 session 不会被关闭）。"""
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> "ChelaiLeClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # 城市接口
    # ------------------------------------------------------------------ #
    def get_city_list(self, hot_only: bool = True) -> list[City]:
        """获取支持的城市列表。

        Args:
            hot_only: 仅返回热门城市，默认 ``True``。完整列表含 500+ 城市。

        Returns:
            城市模型列表。

        Raises:
            NetworkError, APIError: 网络或 API 错误。
        """
        data = self._request(ENDPOINTS["city_list"], signed=False, base=BASE_DOMAIN)
        raw_list = data.get("cityList") or data.get("result") or []
        cities: list[City] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            # isSupport=0 的城市无公交数据，直接跳过
            if _as_int(item.get("isSupport"), default=1) == 0:
                continue
            city = City(
                city_id=str(item.get("cityId", "")),
                name=item.get("cityName", ""),
                pinyin=item.get("pinyin"),
                support_subway=bool(_as_int(item.get("supportSubway"), default=0)),
                is_hot=bool(_as_int(item.get("isHot"), default=0)),
            )
            if hot_only and not city.is_hot:
                continue
            cities.append(city)
        return cities

    def search_city(self, name: str) -> City:
        """通过城市名查找城市 ID。

        支持中文全名（如 ``深圳市``）或简称（``深圳``）查询，
        从热门城市列表中查找（覆盖主流地区）。

        Args:
            name: 城市名关键词。

        Returns:
            匹配到的首个城市对象。

        Raises:
            CityNotFoundError: 未找到匹配城市。
            NetworkError, APIError: 网络或 API 错误。

        Example:
            >>> client.search_city("深圳").city_id
            '014'
        """
        keyword = name.strip().rstrip("市")
        cities = self.get_city_list(hot_only=False)

        # 优先精确匹配，其次前缀/包含匹配，最后拼音匹配
        for city in cities:
            if city.name == keyword:
                return city
        for city in cities:
            if keyword and keyword in city.name:
                return city
        lowered = keyword.lower()
        for city in cities:
            if city.pinyin and lowered == city.pinyin.lower():
                return city
        raise CityNotFoundError(f"未找到城市: {name!r}")

    # ------------------------------------------------------------------ #
    # 线路接口
    # ------------------------------------------------------------------ #
    def search_line(self, city_id: str, keyword: str) -> list[LineInfo]:
        """根据关键词搜索线路（通常返回同名线路的两个方向）。

        Args:
            city_id: 城市编号（如 ``"014"`` 为深圳）。
            keyword: 线路关键词（如 ``"M592"``、``"310路"``）。

        Returns:
            匹配到的线路列表（每个方向为一个 ``LineInfo``）。

        Raises:
            LineNotFoundError: 未匹配到任何线路。
            NetworkError, APIError: 网络或 API 错误。

        Example:
            >>> lines = client.search_line("014", "M592")
            >>> lines[0].name
            'M592路'
        """
        params = {
            "cityId": city_id,
            "localCityId": city_id,
            "key": keyword,
            "supportPhyStn": "true",
        }
        data = self._request(ENDPOINTS["search"], params)
        lines_raw = data.get("result", {}).get("lines", [])

        lines: list[LineInfo] = []
        for item in lines_raw:
            if not isinstance(item, dict):
                continue
            lines.append(
                LineInfo(
                    line_id=str(item.get("lineId", "")),
                    name=item.get("name", ""),
                    direction=int(item.get("direction", 0)),
                    start_station=item.get("startSn", ""),
                    end_station=item.get("endSn", ""),
                    first_time=item.get("firstTime"),
                    last_time=item.get("lastTime"),
                    total_stations=_as_int(item.get("stationNum"), default=None),
                )
            )
        if not lines:
            raise LineNotFoundError(f"未找到线路: {keyword!r}（城市={city_id}）")
        return lines

    def get_line_detail(self, city_id: str, line_id: str) -> list[Station]:
        """获取线路的完整站点列表（单向）。

        Args:
            city_id: 城市编号。
            line_id: 线路 ID（通过 ``search_line`` 获取）。

        Returns:
            该方向所有站点（按 ``order`` 顺序）。

        Raises:
            LineNotFoundError: 线路不存在或无站点信息。
            NetworkError, APIError: 网络或 API 错误。

        Example:
            >>> stations = client.get_line_detail("014", "line_0-014-B4A76C78-C84C-40F3-8D51-E0E29F0F6A8F")
            >>> [s.name for s in stations[:3]]
            ['沙河东站', '名科花园', '深圳大学']
        """
        params = {
            "cityId": city_id,
            "localCityId": city_id,
            "lineId": line_id,
            "lat": "",
            "lng": "",
            "geo_lat": "",
            "geo_lng": "",
        }
        data = self._request(ENDPOINTS["line_detail"], params)
        stations_raw = data.get("stations", [])

        stations: list[Station] = []
        for item in stations_raw:
            if not isinstance(item, dict):
                continue
            stations.append(
                Station(
                    station_id=str(item.get("sId", "")),
                    name=item.get("sn", ""),
                    order=int(item.get("order", 0)),
                    lat=_as_float(item.get("wgsLat")),
                    lng=_as_float(item.get("wgsLng")),
                )
            )
        if not stations:
            raise LineNotFoundError(f"线路无站点信息: {line_id}（城市={city_id}）")
        return stations

    # ------------------------------------------------------------------ #
    # 实时到站接口
    # ------------------------------------------------------------------ #
    def get_realtime_buses(
        self,
        city_id: str,
        line_id: str,
        station_id: str,
        target_order: int,
        lat: float,
        lng: float,
    ) -> RealtimeResult:
        """获取指定站点的实时公交到站信息。

        Args:
            city_id: 城市编号。
            line_id: 线路 ID。
            station_id: 目标站点 ID（从 ``get_line_detail`` 获取）。
            target_order: 目标站点序号（从 1 开始）。
            lat: 目标站点纬度（WGS-84）。
            lng: 目标站点经度（WGS-84）。

        Returns:
            包含线路、车辆列表、刷新间隔的实时查询结果。

        Raises:
            APIError: API 返回错误状态或无数据。
            NetworkError, DecryptionError: 网络或解密错误。

        Example:
            >>> result = client.get_realtime_buses(
            ...     "014", "line_0-014-...", "station_id", 15, 22.5, 113.9
            ... )
            >>> result.nearest_bus.eta_minutes
            3
            >>> result.buses[0].capacity
            0  # 宽松
        """
        params = {
            "cshow": "busDetail",
            "specail": "0",
            "specialType": "undefined",
            "cityId": city_id,
            "localCityId": city_id,
            "lineId": line_id,
            "targetOrder": str(target_order),
            "specialTargetOrder": str(target_order),
            "stationId": station_id,
            "lat": str(lat),
            "lng": str(lng),
            "geo_lat": str(lat),
            "geo_lng": str(lng),
            "userId": "",
            "h5Id": "",
            "unionId": "",
        }
        data = self._request(ENDPOINTS["line_realtime"], params)

        # 解析线路基础信息
        line_raw = data.get("line", {})
        line_info = LineInfo(
            line_id=str(line_raw.get("lineId", line_id)),
            name=line_raw.get("name", ""),
            direction=int(line_raw.get("direction", 0)),
            start_station=line_raw.get("startSn", ""),
            end_station=line_raw.get("endSn", ""),
            first_time=line_raw.get("firstTime"),
            last_time=line_raw.get("lastTime"),
            total_stations=_as_int(line_raw.get("stationsNum")),
        )

        # 解析车辆列表
        buses_raw = data.get("buses", [])
        # (剩余站数, 车辆) —— 上游按 order 升序返回（最远的车在前），
        # 这里按剩余站数升序重排，保证 buses[0] 是最近的一辆车
        ranked: list[tuple[int, BusInfo]] = []

        # 环线取模用的总站数：实时端点的 line 通常不带 stationsNum，
        # 退化时用「车辆最大站序 / 目标站序」的较大值兜底
        total = line_info.total_stations or max(
            [target_order]
            + [
                _as_int(b.get("order"), default=0)
                for b in buses_raw
                if isinstance(b, dict)
            ]
        )

        for bus in buses_raw:
            if not isinstance(bus, dict):
                continue

            bus_order = _as_int(bus.get("order"), default=0)

            # 计算剩余站数（支持环线：车已驶过目标站时绕行一圈取模）
            if bus_order <= target_order:
                remaining = target_order - bus_order
            elif total > 0:
                remaining = (target_order - bus_order) % total
            else:
                remaining = 0

            distance = _as_int(bus.get("distanceToSc"), default=None)

            # 解析 ETA（仅最近 1-2 辆车有 travels）
            eta: Optional[BusETA] = None
            travels = bus.get("travels", [])
            if travels and isinstance(travels[0], dict):
                travel = travels[0]
                travel_time = _as_int(travel.get("travelTime"), default=0)
                if travel_time > 0:
                    eta = BusETA(
                        travel_time=travel_time,
                        arrival_time=_as_int(travel.get("arrivalTime"), default=0),
                        # 上游把到站钟点放在 recommTip（如 "15:21"）
                        display_time=travel.get("recommTip") or travel.get("time"),
                    )

            ranked.append(
                (
                    remaining,
                    BusInfo(
                        bus_id=bus.get("busId", ""),
                        order=bus_order,
                        lat=_as_float(bus.get("lat")),
                        lng=_as_float(bus.get("lng")),
                        speed=_as_float(bus.get("speed")),
                        capacity=_as_int(bus.get("capacity"), default=0),
                        distance_to_station=distance,
                        eta=eta,
                    ),
                )
            )

        ranked.sort(key=lambda pair: pair[0])
        bus_models = [bus for _, bus in ranked]

        # 刷新间隔（秒）—— 上游 refreshInterval 可能为 0/缺失，回退到默认值
        refresh_interval = (
            _as_int(data.get("refreshInterval"), default=0)
            or DEFAULT_REFRESH_INTERVAL
        )

        return RealtimeResult(
            line=line_info,
            target_order=target_order,
            real_data=bool(data.get("realData", True)),
            buses=bus_models,
            refresh_interval=refresh_interval,
        )
