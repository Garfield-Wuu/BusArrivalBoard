"""数据模型测试（纯离线）"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from chelaile_sdk.models import BusETA, BusInfo, City, LineInfo, RealtimeResult, Station


def make_bus(**overrides) -> BusInfo:
    payload = {
        "bus_id": "粤B05981D",
        "order": 15,
        "lat": 22.6295,
        "lng": 113.8127,
        "capacity": 0,
    }
    payload.update(overrides)
    return BusInfo(**payload)


class TestBusInfo:
    def test_eta_minutes_rounds_to_nearest(self):
        bus = make_bus(eta=BusETA(travel_time=310, arrival_time=0))
        assert bus.eta_minutes == 5  # 310s -> 5.17min -> 5

    def test_eta_minutes_rounds_up(self):
        bus = make_bus(eta=BusETA(travel_time=350, arrival_time=0))
        assert bus.eta_minutes == 6

    def test_eta_minutes_none_without_eta(self):
        """远处车辆上游不给预测，必须是 None 而不是 0"""
        assert make_bus().eta_minutes is None

    @pytest.mark.parametrize(
        "capacity,expected",
        [(0, "宽松"), (1, "适中"), (2, "拥挤"), (99, "未知")],
    )
    def test_crowd_level_mapping(self, capacity, expected):
        assert make_bus(capacity=capacity).crowd_level == expected

    def test_missing_required_field_raises(self):
        with pytest.raises(PydanticValidationError):
            BusInfo(order=1, lat=0.0, lng=0.0)  # 缺 bus_id


class TestBusETA:
    def test_display_time_optional(self):
        assert BusETA(travel_time=100, arrival_time=0).display_time is None

    def test_display_time_preserved(self):
        eta = BusETA(travel_time=100, arrival_time=1786951296893, display_time="15:21")
        assert eta.display_time == "15:21"


class TestRealtimeResult:
    def _line(self) -> LineInfo:
        return LineInfo(
            line_id="0755182470300",
            name="M592",
            direction=0,
            start_station="平安居场站",
            end_station="平安居场站",
        )

    def test_nearest_bus_is_first(self):
        near = make_bus(bus_id="near", order=15)
        far = make_bus(bus_id="far", order=2)
        result = RealtimeResult(line=self._line(), target_order=17, buses=[near, far])
        assert result.nearest_bus.bus_id == "near"

    def test_nearest_bus_none_when_empty(self):
        result = RealtimeResult(line=self._line(), target_order=17, buses=[])
        assert result.nearest_bus is None

    def test_defaults(self):
        result = RealtimeResult(line=self._line(), target_order=17)
        assert result.buses == []
        assert result.real_data is True
        assert result.refresh_interval == 60


class TestStationAndCity:
    def test_station_fields(self):
        st = Station(
            station_id="0755-15924",
            name="安翼嘉寓",
            order=17,
            lat=22.6295,
            lng=113.8127,
        )
        assert st.station_id == "0755-15924"
        assert st.order == 17

    def test_city_defaults(self):
        city = City(city_id="014", name="深圳")
        assert city.support_subway is False
        assert city.is_hot is False
