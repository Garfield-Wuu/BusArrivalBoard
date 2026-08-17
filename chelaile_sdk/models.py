"""
车来了 SDK 数据模型

使用 Pydantic 进行数据验证和序列化
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BusETA(BaseModel):
    """公交车到站预测"""

    travel_time: int = Field(..., description="还需秒数")
    arrival_time: int = Field(..., description="到站时间戳(毫秒)")
    display_time: Optional[str] = Field(None, description="推荐显示时间(HH:MM)")


class BusInfo(BaseModel):
    """公交车辆信息"""

    bus_id: str = Field(..., description="车牌号")
    order: int = Field(..., description="当前所在站序号")
    lat: float = Field(..., description="纬度(WGS-84)")
    lng: float = Field(..., description="经度(WGS-84)")
    speed: float = Field(default=0.0, description="速度(km/h)")
    capacity: int = Field(default=0, description="拥挤度 0=宽松 1=适中 2=拥挤")
    distance_to_station: Optional[int] = Field(None, description="距目标站距离(米)")
    eta: Optional[BusETA] = Field(None, description="到站预测(仅最近1-2辆有)")

    @property
    def eta_minutes(self) -> Optional[int]:
        """预计到达分钟数"""
        if self.eta:
            return round(self.eta.travel_time / 60)
        return None

    @property
    def crowd_level(self) -> str:
        """拥挤度文本"""
        return {0: "宽松", 1: "适中", 2: "拥挤"}.get(self.capacity, "未知")


class Station(BaseModel):
    """公交站点"""

    station_id: str = Field(..., description="站点ID")
    name: str = Field(..., description="站点名称")
    order: int = Field(..., description="站点序号")
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")


class LineInfo(BaseModel):
    """线路信息"""

    line_id: str = Field(..., description="线路ID")
    name: str = Field(..., description="线路名称")
    direction: int = Field(..., description="方向 0/1")
    start_station: str = Field(..., description="起点站")
    end_station: str = Field(..., description="终点站")
    first_time: Optional[str] = Field(None, description="首班时间")
    last_time: Optional[str] = Field(None, description="末班时间")
    total_stations: Optional[int] = Field(None, description="总站数")


class RealtimeResult(BaseModel):
    """实时查询结果"""

    line: LineInfo
    target_order: int = Field(..., description="目标站点序号")
    real_data: bool = Field(True, description="是否有GPS实时数据")
    buses: list[BusInfo] = Field(default_factory=list)
    refresh_interval: int = Field(60, description="建议刷新间隔(秒)")

    @property
    def nearest_bus(self) -> Optional[BusInfo]:
        """最近的一辆车"""
        return self.buses[0] if self.buses else None


class City(BaseModel):
    """城市信息"""

    city_id: str
    name: str
    pinyin: Optional[str] = None
    support_subway: bool = False
    is_hot: bool = False
