"""
多站点实时监控模块

提供 BusMonitor 类，负责把配置中的目标站点（城市/线路/站点名称）解析成
API 所需的 ID 组合，并按配置的刷新间隔轮询实时到站数据。

Example:
    >>> from bus_arrival_board.config import load_config
    >>> from bus_arrival_board.monitor import BusMonitor
    >>> cfg = load_config("config/shenzhen_m592.yaml")
    >>> monitor = BusMonitor(cfg)
    >>> monitor.resolve_targets()
    >>> for target, result in monitor.poll_once():
    ...     print(target.display_name(), len(result.buses))
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from chelaile_sdk.client import ChelaiLeClient
from chelaile_sdk.exceptions import (
    APIError,
    CityNotFoundError,
    LineNotFoundError,
    NetworkError,
    StationNotFoundError,
)
from chelaile_sdk.models import RealtimeResult

from .config import AppConfig, WatchTarget

logger = logging.getLogger(__name__)

__all__ = ["BusMonitor", "ResolvedTarget", "remaining_stops"]


def remaining_stops(
    bus_order: int,
    target_order: int,
    total_stations: Optional[int],
) -> Optional[int]:
    """计算公交车距目标站点的剩余站数（支持环线）

    普通线路：车辆站序 <= 目标站序时直接相减。
    环线：车辆已驶过目标站时，需要绕行一圈，用总站数取模。

    Args:
        bus_order: 车辆当前所在站序号（从 1 开始）
        target_order: 目标站点序号（从 1 开始）
        total_stations: 线路总站数，缺失时无法计算环线绕行

    Returns:
        剩余站数；当车辆已驶过目标站且 total_stations 缺失时返回 None

    Example:
        >>> remaining_stops(2, 17, 26)   # 普通情况
        15
        >>> remaining_stops(20, 17, 26)  # 环线绕行
        23
        >>> remaining_stops(20, 17, None)  # 无总站数
        None
    """
    if bus_order <= target_order:
        return target_order - bus_order

    # 车辆已驶过目标站，需要环线取模
    if not total_stations or total_stations <= 0:
        logger.debug(
            "无法计算环线剩余站数: bus_order=%s > target_order=%s 但 total_stations=%s",
            bus_order,
            target_order,
            total_stations,
        )
        return None

    return (target_order - bus_order) % total_stations


@dataclass
class ResolvedTarget:
    """已解析的监控目标（缓存 API 所需的全部参数）

    Attributes:
        target: 原始配置目标
        city_id: 城市编号
        line_id: 线路 ID
        station_id: 站点 ID
        target_order: 站点序号
        lat: 站点纬度（WGS-84）
        lng: 站点经度（WGS-84）
        line_name: 线路名称（用于显示）
        station_name: 站点全名（用于显示）
        total_stations: 线路总站数
    """
    target: WatchTarget
    city_id: str
    line_id: str
    station_id: str
    target_order: int
    lat: float
    lng: float
    line_name: str = ""
    station_name: str = ""
    total_stations: Optional[int] = None


class BusMonitor:
    """多站点公交实时监控器

    负责名称到 ID 的解析（带缓存）以及按间隔轮询实时数据。
    单次轮询失败不会中断循环，仅记录日志。

    Attributes:
        config: 应用配置
        client: 车来了 API 客户端
        resolved: 已解析的目标列表（调用 resolve_targets 后填充）
    """

    def __init__(
        self,
        config: AppConfig,
        client: Optional[ChelaiLeClient] = None,
    ) -> None:
        """初始化监控器

        Args:
            config: 应用配置对象
            client: 可选的 API 客户端，默认自动创建
        """
        self.config = config
        self.client = client or ChelaiLeClient()
        self.resolved: list[ResolvedTarget] = []
        # 城市名 -> city_id 缓存，避免重复请求
        self._city_cache: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # 目标解析
    # ------------------------------------------------------------------ #
    def resolve_targets(self, force: bool = False) -> list[ResolvedTarget]:
        """把配置中的目标名称解析成 API 所需的 ID 组合并缓存

        Args:
            force: 为 True 时强制重新解析（忽略已有缓存）

        Returns:
            已解析的目标列表

        Raises:
            ValueError: 某个目标解析失败，错误信息包含目标标识和失败步骤

        Example:
            >>> monitor.resolve_targets()
            [ResolvedTarget(...)]
        """
        if self.resolved and not force:
            logger.debug("目标已解析，跳过（共 %d 个）", len(self.resolved))
            return self.resolved

        resolved: list[ResolvedTarget] = []

        for idx, target in enumerate(self.config.targets):
            label = f"target[{idx}] ({target.display_name()})"
            logger.info("正在解析 %s", label)
            resolved.append(self._resolve_one(target, label))

        self.resolved = resolved
        logger.info("目标解析完成，共 %d 个", len(resolved))
        return resolved

    def _resolve_one(self, target: WatchTarget, label: str) -> ResolvedTarget:
        """解析单个监控目标

        Args:
            target: 配置中的监控目标
            label: 用于错误信息的目标标识

        Returns:
            解析后的目标对象

        Raises:
            ValueError: 城市/线路/站点任一步骤解析失败
        """
        # --- 步骤 1: 解析城市 ---
        city_id = self._city_cache.get(target.city)
        if city_id is None:
            try:
                city = self.client.search_city(target.city)
            except CityNotFoundError as exc:
                raise ValueError(
                    f"{label} 解析失败 [步骤1/3 城市]: 未找到城市 '{target.city}' - {exc}"
                ) from exc
            except (APIError, NetworkError) as exc:
                raise ValueError(
                    f"{label} 解析失败 [步骤1/3 城市]: 查询城市 '{target.city}' 时出错 - {exc}"
                ) from exc
            city_id = city.city_id
            self._city_cache[target.city] = city_id
            logger.debug("城市 '%s' -> city_id=%s", target.city, city_id)

        # --- 步骤 2: 解析线路 ---
        try:
            lines = self.client.search_line(city_id, target.line)
        except LineNotFoundError as exc:
            raise ValueError(
                f"{label} 解析失败 [步骤2/3 线路]: 未找到线路 '{target.line}' - {exc}"
            ) from exc
        except (APIError, NetworkError) as exc:
            raise ValueError(
                f"{label} 解析失败 [步骤2/3 线路]: 查询线路 '{target.line}' 时出错 - {exc}"
            ) from exc

        if not lines:
            raise ValueError(
                f"{label} 解析失败 [步骤2/3 线路]: "
                f"城市 '{target.city}' 中未找到线路 '{target.line}'"
            )

        # 按 direction 过滤（未指定时取第一条）
        line_obj = lines[0]
        if target.direction is not None:
            matched = [ln for ln in lines if ln.direction == target.direction]
            if not matched:
                available = sorted({ln.direction for ln in lines})
                raise ValueError(
                    f"{label} 解析失败 [步骤2/3 线路]: "
                    f"线路 '{target.line}' 无 direction={target.direction} 的方向，"
                    f"可用方向: {available}"
                )
            line_obj = matched[0]

        logger.debug(
            "线路 '%s' -> line_id=%s direction=%s",
            target.line,
            line_obj.line_id,
            line_obj.direction,
        )

        # --- 步骤 3: 解析站点（子串匹配）---
        try:
            stations = self.client.get_line_detail(city_id, line_obj.line_id)
        except (LineNotFoundError, APIError, NetworkError) as exc:
            raise ValueError(
                f"{label} 解析失败 [步骤3/3 站点]: "
                f"获取线路 '{target.line}' 站点列表时出错 - {exc}"
            ) from exc

        station_obj = None
        for st in stations:
            if target.station in st.name:
                station_obj = st
                break

        if station_obj is None:
            names = [st.name for st in stations]
            preview = "、".join(names[:10])
            more = f"（共 {len(names)} 站）" if len(names) > 10 else ""
            raise ValueError(
                f"{label} 解析失败 [步骤3/3 站点]: "
                f"线路 '{target.line}' 上未找到包含 '{target.station}' 的站点。"
                f"可选站点: {preview}{more}"
            )

        logger.debug(
            "站点 '%s' -> station_id=%s order=%s",
            target.station,
            station_obj.station_id,
            station_obj.order,
        )

        return ResolvedTarget(
            target=target,
            city_id=city_id,
            line_id=line_obj.line_id,
            station_id=station_obj.station_id,
            target_order=station_obj.order,
            lat=station_obj.lat,
            lng=station_obj.lng,
            line_name=line_obj.name,
            station_name=station_obj.name,
            total_stations=line_obj.total_stations or len(stations),
        )

    # ------------------------------------------------------------------ #
    # 轮询
    # ------------------------------------------------------------------ #
    def poll_once(self) -> list[tuple[WatchTarget, RealtimeResult]]:
        """对所有已解析目标各查询一次实时到站数据

        未解析时会自动调用 resolve_targets()。单个目标查询失败会记录
        日志并跳过，不影响其他目标。

        Returns:
            (目标配置, 实时结果) 元组列表，顺序与配置一致

        Example:
            >>> results = monitor.poll_once()
            >>> for target, result in results:
            ...     print(target.display_name(), result.buses[0].eta_minutes)
        """
        if not self.resolved:
            self.resolve_targets()

        results: list[tuple[WatchTarget, RealtimeResult]] = []

        for rt in self.resolved:
            name = rt.target.display_name()
            try:
                result = self.client.get_realtime_buses(
                    city_id=rt.city_id,
                    line_id=rt.line_id,
                    station_id=rt.station_id,
                    target_order=rt.target_order,
                    lat=rt.lat,
                    lng=rt.lng,
                )
            except (APIError, NetworkError, StationNotFoundError) as exc:
                logger.warning("查询 %s 失败，已跳过: %s", name, exc)
                continue
            except Exception as exc:  # noqa: BLE001 - 单点失败不应中断整轮
                logger.exception("查询 %s 时发生未预期错误，已跳过: %s", name, exc)
                continue

            logger.debug("查询 %s 成功，返回 %d 辆车", name, len(result.buses))
            results.append((rt.target, result))

        return results

    def run(
        self,
        callback: Callable[[list[tuple[WatchTarget, RealtimeResult]]], None],
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """循环轮询并回调，直到 stop_event 置位或收到 Ctrl+C

        单轮失败（含 callback 抛错）只记录日志，不中断循环。

        Args:
            callback: 每轮结果的处理函数，入参为 poll_once() 的返回值
            stop_event: 可选的停止信号，置位后优雅退出

        Example:
            >>> monitor.run(lambda results: print(len(results)))
        """
        interval = self.config.refresh_interval
        logger.info(
            "开始监控 %d 个目标，刷新间隔 %d 秒（Ctrl+C 停止）",
            len(self.config.targets),
            interval,
        )

        try:
            # 首轮前先解析，解析失败应直接向上抛出（配置问题，无法自愈）
            self.resolve_targets()

            while True:
                if stop_event is not None and stop_event.is_set():
                    logger.info("收到停止信号，监控退出")
                    return

                try:
                    results = self.poll_once()
                    callback(results)
                except Exception as exc:  # noqa: BLE001 - 保证循环不中断
                    logger.exception("本轮监控失败，将在 %d 秒后重试: %s", interval, exc)

                # 分片 sleep，让 stop_event 能被及时响应
                if not self._sleep(interval, stop_event):
                    logger.info("收到停止信号，监控退出")
                    return

        except KeyboardInterrupt:
            logger.info("收到 Ctrl+C，监控已优雅停止")

    @staticmethod
    def _sleep(seconds: int, stop_event: Optional[threading.Event]) -> bool:
        """可中断的 sleep

        Args:
            seconds: 总休眠秒数
            stop_event: 可选停止信号

        Returns:
            True 表示正常睡完，False 表示被 stop_event 打断
        """
        if stop_event is None:
            time.sleep(seconds)
            return True

        # Event.wait 返回 True 表示被置位
        return not stop_event.wait(timeout=seconds)
