"""配置加载测试（纯离线，使用 tmp_path 写临时 YAML）"""

import pytest
import yaml

from bus_arrival_board.config import AppConfig, load_config


def write_yaml(tmp_path, data) -> str:
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return str(path)


class TestFlatFormat:
    """旧的单站点扁平格式必须继续可用（向后兼容）"""

    def test_flat_becomes_single_target(self, tmp_path):
        path = write_yaml(tmp_path, {"city": "深圳", "line": "M592", "station": "安翼嘉寓"})
        cfg = load_config(path)
        assert isinstance(cfg, AppConfig)
        assert len(cfg.targets) == 1
        assert cfg.targets[0].city == "深圳"
        assert cfg.targets[0].line == "M592"
        assert cfg.targets[0].station == "安翼嘉寓"

    def test_defaults_applied(self, tmp_path):
        path = write_yaml(tmp_path, {"city": "深圳", "line": "M592", "station": "安翼嘉寓"})
        cfg = load_config(path)
        assert cfg.refresh_interval == 60
        assert cfg.display.max_buses == 3
        assert cfg.notification.enabled is False


class TestTargetsFormat:
    def test_multiple_targets_parsed(self, tmp_path):
        path = write_yaml(
            tmp_path,
            {
                "refresh_interval": 90,
                "targets": [
                    {"city": "深圳", "line": "M592", "station": "安翼嘉寓", "alias": "上班"},
                    {"city": "深圳", "line": "M592", "station": "后瑞地铁站"},
                ],
            },
        )
        cfg = load_config(path)
        assert len(cfg.targets) == 2
        assert cfg.refresh_interval == 90
        assert cfg.targets[0].alias == "上班"
        assert cfg.targets[1].alias is None

    def test_display_overrides(self, tmp_path):
        path = write_yaml(
            tmp_path,
            {
                "targets": [{"city": "深圳", "line": "M592", "station": "安翼嘉寓"}],
                "display": {"max_buses": 5, "show_crowd": False},
            },
        )
        cfg = load_config(path)
        assert cfg.display.max_buses == 5
        assert cfg.display.show_crowd is False


class TestValidation:
    def test_refresh_interval_below_floor_rejected(self, tmp_path):
        """低于 30 秒会给上游造成压力，必须拒绝"""
        path = write_yaml(
            tmp_path,
            {"city": "深圳", "line": "M592", "station": "安翼嘉寓", "refresh_interval": 5},
        )
        with pytest.raises(ValueError):
            load_config(path)

    def test_missing_targets_rejected(self, tmp_path):
        path = write_yaml(tmp_path, {"refresh_interval": 60})
        with pytest.raises(ValueError):
            load_config(path)

    def test_incomplete_target_rejected(self, tmp_path):
        path = write_yaml(tmp_path, {"city": "深圳", "line": "M592"})  # 缺 station
        with pytest.raises(ValueError):
            load_config(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises((FileNotFoundError, ValueError)):
            load_config(str(tmp_path / "nope.yaml"))


class TestShippedConfigs:
    """仓库自带的示例配置必须真的能加载"""

    def test_single_station_example(self):
        cfg = load_config("config/shenzhen_m592.yaml")
        assert len(cfg.targets) == 1

    def test_multi_station_example(self):
        cfg = load_config("config/multi_station.yaml")
        assert len(cfg.targets) == 2
        assert cfg.refresh_interval >= 30
