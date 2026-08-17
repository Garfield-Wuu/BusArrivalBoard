"""依赖与环境健全性测试

这些测试锁住真实踩过的坑：请求头声明了 br 压缩，但 brotli 解码库
不在依赖里时，响应会变成无法解码的乱码字节，且只在干净环境暴露。
"""

import importlib

import pytest

from chelaile_sdk.constants import REQUEST_HEADERS


class TestBrotliAvailability:
    def test_accept_encoding_declares_br(self):
        """请求头是服务端指纹校验的一部分，br 不能删"""
        assert "br" in REQUEST_HEADERS["Accept-Encoding"]

    def test_brotli_decoder_importable(self):
        """声明了 br 就必须能解码 br，否则拿到的是乱码字节而非 JSON"""
        try:
            importlib.import_module("brotli")
        except ImportError:  # pragma: no cover
            try:
                importlib.import_module("brotlicffi")
            except ImportError:
                pytest.fail(
                    "缺少 brotli 解码库：Accept-Encoding 含 br，"
                    "但没有解码器会导致响应变成乱码。请安装 brotli。"
                )

    def test_urllib3_negotiates_br(self):
        """确认 urllib3 在装了 brotli 后确实会协商 br"""
        from urllib3.util.request import ACCEPT_ENCODING

        assert "br" in ACCEPT_ENCODING


class TestRequiredDependencies:
    @pytest.mark.parametrize(
        "module",
        ["requests", "cryptography", "yaml", "click", "rich", "pydantic"],
    )
    def test_dependency_importable(self, module):
        importlib.import_module(module)

    def test_pydantic_is_v2(self):
        """models.py 使用 pydantic v2 API"""
        import pydantic

        assert pydantic.VERSION.startswith("2."), f"需要 pydantic v2，当前 {pydantic.VERSION}"


class TestPythonCompatibility:
    def test_declared_floor_is_importable(self):
        """项目声明支持 3.9；SDK 必须能在最低版本导入成功

        历史问题：exceptions.py 用了 `int | None`（3.10+ 语法）却没有
        `from __future__ import annotations`，导致 3.9 下导入即崩。
        """
        import bus_arrival_board.cli
        import bus_arrival_board.config
        import bus_arrival_board.monitor
        import chelaile_sdk

        assert chelaile_sdk.ChelaiLeClient is not None

    def test_apierror_runtime_instantiation(self):
        """带 Optional 注解的构造函数要能在运行时真正实例化"""
        from chelaile_sdk import APIError

        err = APIError("boom", status_code=400)
        assert "400" in str(err)
