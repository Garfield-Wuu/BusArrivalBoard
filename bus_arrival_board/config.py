"""
配置加载与管理模块

支持两种配置格式：
1. 单站点扁平格式（向后兼容）- city/line/station 在顶层
2. 多站点格式 - targets: [{city, line, station, ...}, ...]

Example:
    >>> from bus_arrival_board.config import load_config
    >>> cfg = load_config("config/shenzhen_m592.yaml")
    >>> print(cfg.targets[0].city)
    '深圳'
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class DisplayConfig(BaseModel):
    """显示配置

    Attributes:
        max_buses: 最多显示前几辆车，默认 3
        show_crowd: 是否显示拥挤度，默认 True
        show_distance: 是否显示距离，默认 True
        show_gps_coords: 是否显示 GPS 坐标（调试用），默认 False
    """

    max_buses: int = Field(default=3, ge=1, description="最多显示前几辆车")
    show_crowd: bool = Field(default=True, description="是否显示拥挤度")
    show_distance: bool = Field(default=True, description="是否显示距离")
    show_gps_coords: bool = Field(default=False, description="是否显示GPS坐标（调试用）")


class NotificationConfig(BaseModel):
    """通知配置

    Attributes:
        enabled: 是否启用通知，默认 False
        threshold_minutes: 车辆还有X分钟时通知，默认 5
        sound: 是否播放提示音，默认 True
    """

    enabled: bool = Field(default=False, description="是否启用通知")
    threshold_minutes: int = Field(default=5, ge=1, description="车辆还有X分钟时通知")
    sound: bool = Field(default=True, description="是否播放提示音")


class WatchTarget(BaseModel):
    """监控目标站点

    Attributes:
        city: 城市名称，如 "深圳"
        line: 线路名称，如 "M592"
        station: 站点名称，如 "安翼嘉寓"
        direction: 方向（0 或 1），None 表示自动选择第一个方向
        alias: 别名，用于显示和日志（可选）
    """

    city: str = Field(..., description="城市名称")
    line: str = Field(..., description="线路名称")
    station: str = Field(..., description="站点名称")
    direction: Optional[int] = Field(default=None, ge=0, le=1, description="方向 0/1，None=自动")
    alias: Optional[str] = Field(default=None, description="别名，用于显示")

    def display_name(self) -> str:
        """返回用于显示的名称（优先使用 alias）"""
        if self.alias:
            return self.alias
        return f"{self.city} {self.line} {self.station}"


class AppConfig(BaseModel):
    """应用配置

    Attributes:
        targets: 监控目标列表
        refresh_interval: 刷新间隔（秒），必须 >= 30
        display: 显示配置
        notification: 通知配置
    """

    targets: list[WatchTarget] = Field(..., min_length=1, description="监控目标列表")
    refresh_interval: int = Field(default=60, ge=30, description="刷新间隔（秒）")
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)

    @field_validator("refresh_interval")
    @classmethod
    def validate_refresh_interval(cls, v: int) -> int:
        """验证刷新间隔，必须 >= 30 秒以保护上游服务"""
        if v < 30:
            raise ValueError(
                f"refresh_interval 必须 >= 30 秒（当前值：{v}）。"
                "较短的刷新间隔可能导致被限流或封禁。"
            )
        return v


# 默认配置文件搜索路径（优先级从高到低）
DEFAULT_CONFIG_PATHS = [
    "./config.yaml",
    "./config/config.yaml",
    "~/.config/bus_arrival_board/config.yaml",
    "/etc/bus_arrival_board/config.yaml",
]


def load_config(path: str | Path) -> AppConfig:
    """加载配置文件

    支持两种格式：
    1. 单站点扁平格式（向后兼容）：
       ```yaml
       city: "深圳"
       line: "M592"
       station: "安翼嘉寓"
       refresh_interval: 60
       display:
         max_buses: 3
       ```

    2. 多站点格式：
       ```yaml
       targets:
         - city: "深圳"
           line: "M592"
           station: "安翼嘉寓"
           alias: "回家"
         - city: "深圳"
           line: "M591"
           station: "科技园"
       refresh_interval: 60
       ```

    Args:
        path: 配置文件路径（支持 ~ 展开）

    Returns:
        解析后的应用配置对象

    Raises:
        FileNotFoundError: 配置文件不存在
        ValueError: 配置格式错误或验证失败
        yaml.YAMLError: YAML 解析失败

    Example:
        >>> cfg = load_config("config/shenzhen_m592.yaml")
        >>> print(cfg.targets[0].city)
        '深圳'
    """
    # 展开用户目录
    config_path = Path(path).expanduser().resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    # 读取 YAML
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data: dict[str, Any] = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 解析失败: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError("配置文件根节点必须是字典")

    # 检测并转换为统一格式
    if "targets" not in raw_data:
        # 单站点扁平格式 -> 转换为多站点格式
        if not all(k in raw_data for k in ("city", "line", "station")):
            raise ValueError(
                "单站点配置必须包含 city, line, station 字段，" "或使用多站点格式（targets 列表）"
            )

        # 提取单站点信息
        target_data = {
            "city": raw_data.pop("city"),
            "line": raw_data.pop("line"),
            "station": raw_data.pop("station"),
        }

        # 可选字段
        if "direction" in raw_data:
            target_data["direction"] = raw_data.pop("direction")
        if "alias" in raw_data:
            target_data["alias"] = raw_data.pop("alias")

        # 将单站点包装成 targets 列表
        raw_data["targets"] = [target_data]

    # 使用 Pydantic 验证和解析
    try:
        return AppConfig(**raw_data)
    except Exception as exc:
        raise ValueError(f"配置验证失败: {exc}") from exc


def find_config() -> Path:
    """按默认搜索路径查找配置文件

    Returns:
        找到的第一个存在的配置文件路径

    Raises:
        FileNotFoundError: 所有默认路径都不存在配置文件

    Example:
        >>> config_path = find_config()
        >>> cfg = load_config(config_path)
    """
    for path_str in DEFAULT_CONFIG_PATHS:
        path = Path(path_str).expanduser().resolve()
        if path.exists():
            return path

    # 所有路径都不存在
    search_list = "\n  ".join(DEFAULT_CONFIG_PATHS)
    raise FileNotFoundError(
        f"未找到配置文件，已搜索以下路径：\n  {search_list}\n\n"
        f"请创建配置文件或使用 --config 参数指定路径"
    )
