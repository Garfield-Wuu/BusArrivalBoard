"""
EPD 墨水屏自动更新器

高层封装，集成查询、渲染、BLE 传输为一体，支持守护进程模式。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bus_arrival_board.config import AppConfig
from bus_arrival_board.epd.ble_client import EPDClient, EPDError
from bus_arrival_board.epd.renderer import BusDisplayRenderer
from bus_arrival_board.monitor import BusMonitor

logger = logging.getLogger(__name__)


@dataclass
class UpdateStats:
    """更新统计"""

    total_updates: int = 0
    successful_updates: int = 0
    failed_updates: int = 0
    last_update_time: Optional[datetime] = None
    last_error: Optional[str] = None


class EPDUpdater:
    """墨水屏自动更新器

    查询公交实时数据 → 渲染图片 → 通过 BLE 发送到墨水屏。
    支持单次更新和循环守护进程模式。

    Example:
        >>> import asyncio
        >>> from bus_arrival_board.config import load_config
        >>> from bus_arrival_board.epd import EPDClient, BusDisplayRenderer, EPDUpdater
        >>>
        >>> cfg = load_config("config.yaml")
        >>> epd = EPDClient()
        >>> await epd.connect("NRF_EPD_1234")
        >>> await epd.init(driver=0)  # UC8176 黑白
        >>>
        >>> renderer = BusDisplayRenderer(400, 300)
        >>> updater = EPDUpdater(cfg, epd, renderer)
        >>>
        >>> # 单次更新
        >>> await updater.update_once()
        >>>
        >>> # 守护进程（每 5 分钟自动刷新）
        >>> await updater.run_loop(interval_seconds=300)
    """

    def __init__(
        self,
        config: AppConfig,
        epd_client: EPDClient,
        renderer: BusDisplayRenderer,
    ):
        """初始化更新器

        Args:
            config: 应用配置（包含监控目标）
            epd_client: 已连接的 EPD 客户端
            renderer: 渲染引擎实例
        """
        self.config = config
        self.epd = epd_client
        self.renderer = renderer
        self.monitor = BusMonitor(config)
        self.monitor.resolve_targets()
        self.stats = UpdateStats()
        self._should_stop = False

    async def update_once(self) -> bool:
        """执行一次完整更新：查询 → 渲染 → 发送

        Returns:
            bool: 是否更新成功

        Raises:
            EPDError: BLE 传输失败时抛出（不会静默吞掉）
        """
        self.stats.total_updates += 1
        start_time = time.monotonic()

        try:
            # 1. 查询实时数据
            results = list(self.monitor.poll_once())
            if not results:
                logger.warning("查询无结果，跳过本次更新")
                self.stats.last_error = "查询无结果"
                self.stats.failed_updates += 1
                return False

            target, result = results[0]  # 取第一个目标
            logger.info(
                "查询成功: %s @ %s, 车辆数=%d",
                target.line,
                target.station,
                len(result.buses),
            )

            # 2. 渲染图片
            img = self.renderer.render(result, target)
            pixels = self.renderer.to_bytes(img)
            logger.info("渲染完成: %dx%d, %d 字节", img.width, img.height, len(pixels))

            # 3. 发送到墨水屏
            await self.epd.write_image(pixels)
            await self.epd.refresh()

            elapsed = time.monotonic() - start_time
            logger.info("✅ 墨水屏更新成功，耗时 %.2f 秒", elapsed)

            self.stats.successful_updates += 1
            self.stats.last_update_time = datetime.now()
            self.stats.last_error = None
            return True

        except EPDError as exc:
            # BLE 错误不捕获，让上层决定是否重试
            logger.error("墨水屏传输失败: %s", exc)
            self.stats.failed_updates += 1
            self.stats.last_error = str(exc)
            raise

        except Exception as exc:
            # 其他错误（查询、渲染）记录但不中断循环
            logger.exception("更新失败: %s", exc)
            self.stats.failed_updates += 1
            self.stats.last_error = str(exc)
            return False

    async def run_loop(
        self,
        interval_seconds: int = 300,
        max_retries: int = 3,
    ) -> None:
        """守护进程模式：循环自动刷新

        Args:
            interval_seconds: 刷新间隔（秒），默认 300（5 分钟）
            max_retries: 单次更新失败时的重试次数，默认 3

        Note:
            墨水屏建议 ≥ 5 分钟刷新一次，避免残影。
            用 Ctrl+C 或 stop() 方法优雅退出。
        """
        logger.info("墨水屏守护进程启动，刷新间隔=%d秒", interval_seconds)
        self._should_stop = False

        while not self._should_stop:
            retry_count = 0
            success = False

            while retry_count < max_retries and not self._should_stop:
                try:
                    success = await self.update_once()
                    if success:
                        break
                except EPDError as exc:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(
                            "BLE 传输失败（%d/%d），%.1f秒后重试: %s",
                            retry_count,
                            max_retries,
                            5.0,
                            exc,
                        )
                        await asyncio.sleep(5.0)
                    else:
                        logger.error("达到最大重试次数，跳过本次更新")

            if not success:
                logger.warning("本轮更新失败，等待下一轮")

            # 等待下一轮
            if not self._should_stop:
                logger.debug("下次更新将在 %d 秒后", interval_seconds)
                try:
                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    logger.info("收到取消信号，退出守护进程")
                    break

        logger.info("墨水屏守护进程已停止")
        logger.info(
            "统计: 总计=%d, 成功=%d, 失败=%d",
            self.stats.total_updates,
            self.stats.successful_updates,
            self.stats.failed_updates,
        )

    def stop(self) -> None:
        """优雅停止守护进程"""
        logger.info("收到停止信号")
        self._should_stop = True

    def get_stats(self) -> UpdateStats:
        """获取更新统计

        Returns:
            UpdateStats: 统计信息（总数、成功数、失败数、最后更新时间）
        """
        return self.stats
