"""
命令行工具入口
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from chelaile_sdk import ChelaiLeClient, CityNotFoundError, LineNotFoundError

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """🚌 BusArrivalBoard - 实时公交到站显示系统"""
    pass


@main.command()
@click.option("--city", required=True, help="城市名称，如：深圳")
@click.option("--line", required=True, help="线路名称，如：M592")
@click.option("--station", required=True, help="站点名称，如：安翼嘉寓")
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
def query(city: str, line: str, station: str, format: str):
    """查询公交实时到站信息（单次查询）"""

    try:
        client = ChelaiLeClient()

        with console.status(f"[bold green]正在查询 {city} {line}路 {station}站..."):
            # 搜索城市
            city_obj = client.search_city(city)

            # 搜索线路
            lines = client.search_line(city_obj.city_id, line)
            if not lines:
                console.print(f"[red]❌ 未找到线路 {line}")
                sys.exit(1)

            line_obj = lines[0]

            # 获取站点列表
            stations = client.get_line_detail(city_obj.city_id, line_obj.line_id)

            # 查找目标站点
            target = None
            for st in stations:
                if station in st.name:
                    target = st
                    break

            if not target:
                console.print(f"[red]❌ 未找到站点 {station}")
                sys.exit(1)

            # 获取实时数据
            result = client.get_realtime_buses(
                city_id=city_obj.city_id,
                line_id=line_obj.line_id,
                station_id=target.station_id,
                target_order=target.order,
                lat=target.lat,
                lng=target.lng,
            )

        # 输出结果
        if format == "json":
            import json

            print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        else:
            _display_result(result, line_obj, target)

    except CityNotFoundError:
        console.print(f"[red]❌ 城市 '{city}' 不存在或暂不支持")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]❌ 查询失败: {e}")
        sys.exit(1)


@main.command()
@click.option("--city", required=True, help="城市名称")
@click.option("--line", required=True, help="线路名称")
@click.option("--station", required=True, help="站点名称")
@click.option("--interval", default=60, help="刷新间隔（秒），默认60")
def monitor(city: str, line: str, station: str, interval: int):
    """实时监控模式（持续刷新）"""

    try:
        client = ChelaiLeClient()

        # 初始化查询（获取固定信息）
        with console.status("[bold green]初始化..."):
            city_obj = client.search_city(city)
            lines = client.search_line(city_obj.city_id, line)
            if not lines:
                console.print(f"[red]❌ 未找到线路 {line}")
                sys.exit(1)

            line_obj = lines[0]
            stations = client.get_line_detail(city_obj.city_id, line_obj.line_id)

            target = None
            for st in stations:
                if station in st.name:
                    target = st
                    break

            if not target:
                console.print(f"[red]❌ 未找到站点 {station}")
                sys.exit(1)

        console.print(f"[green]✓ 开始监控: {line_obj.name} - {target.name}")
        console.print(f"[dim]刷新间隔: {interval}秒 | 按 Ctrl+C 停止\n")

        # 持续监控
        while True:
            try:
                result = client.get_realtime_buses(
                    city_id=city_obj.city_id,
                    line_id=line_obj.line_id,
                    station_id=target.station_id,
                    target_order=target.order,
                    lat=target.lat,
                    lng=target.lng,
                )

                console.clear()
                _display_result(result, line_obj, target)
                console.print(
                    f"\n[dim]下次刷新: {interval}秒后 | {datetime.now().strftime('%H:%M:%S')}"
                )

                time.sleep(interval)

            except KeyboardInterrupt:
                console.print("\n[yellow]监控已停止")
                break
            except Exception as e:
                console.print(f"[red]刷新失败: {e}")
                time.sleep(interval)

    except Exception as e:
        console.print(f"[red]❌ 初始化失败: {e}")
        sys.exit(1)


@main.command()
@click.option("--hot-only", is_flag=True, help="仅显示热门城市")
def cities(hot_only: bool):
    """列出支持的城市"""

    try:
        client = ChelaiLeClient()
        cities = client.get_city_list(hot_only=hot_only)

        table = Table(title="支持的城市列表")
        table.add_column("城市ID", style="cyan")
        table.add_column("城市名称", style="green")
        table.add_column("拼音", style="dim")
        table.add_column("地铁", style="yellow")

        for city in cities[:50]:  # 限制显示前50个
            table.add_row(
                city.city_id, city.name, city.pinyin or "-", "✓" if city.support_subway else ""
            )

        console.print(table)
        console.print(f"\n[dim]共 {len(cities)} 个城市")

    except Exception as e:
        console.print(f"[red]❌ 获取失败: {e}")
        sys.exit(1)


def _display_result(result, line_obj, target):
    """格式化显示查询结果"""

    # 标题
    title = f"🚌 {line_obj.name} → {line_obj.end_station}"
    subtitle = f"当前站: {target.name} (第{target.order}站)"

    console.print(Panel(f"{title}\n{subtitle}", border_style="green"))

    # 公交列表
    if not result.buses:
        console.print("[yellow]当前无车辆在途")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("车牌号", style="cyan")
    table.add_column("当前位置", style="yellow")
    table.add_column("预计到达", style="green")
    table.add_column("拥挤度", style="blue")

    for i, bus in enumerate(result.buses[:5], 1):  # 最多显示5辆
        if bus.eta and bus.eta_minutes is not None:
            eta_text = f"{bus.eta_minutes}分钟"
            if bus.eta.display_time:
                eta_text += f" ({bus.eta.display_time})"
        else:
            eta_text = "暂无预测"

        table.add_row(str(i), bus.bus_id, f"第{bus.order}站", eta_text, bus.crowd_level)

    console.print(table)
    console.print(f"\n[dim]数据源: {'GPS实时' if result.real_data else '时刻表估算'}")


@main.group(name="epd")
def epd_group():
    """🖥️  墨水屏硬件控制（需要安装可选依赖 [epd]）"""
    pass


@epd_group.command(name="scan")
@click.option("--timeout", default=10.0, help="扫描超时（秒），默认 10")
def epd_scan(timeout: float):
    """扫描附近的 EPD 蓝牙设备"""
    import asyncio

    try:
        from bus_arrival_board.epd import EPDClient, EPDConnectionError, EPDError
    except ImportError as exc:
        console.print(f"[red]❌ EPD 功能不可用: {exc}")
        console.print("[yellow]请安装可选依赖: pip install bus-arrival-board[epd]")
        sys.exit(1)

    async def _scan():
        try:
            with console.status(f"[bold green]正在扫描 EPD 设备（超时 {timeout}秒）..."):
                devices = await EPDClient.scan(timeout=timeout)

            if not devices:
                console.print("[yellow]⚠️  未发现 EPD 设备")
                console.print("[dim]提示: 确保设备已开机且蓝牙已启用")
                return

            table = Table(title=f"发现 {len(devices)} 个 EPD 设备")
            table.add_column("设备名称", style="cyan")
            table.add_column("MAC 地址", style="green")

            for dev in devices:
                table.add_row(dev.name or "未知", dev.address)

            console.print(table)

        except EPDConnectionError as exc:
            console.print(f"[red]❌ 扫描失败: {exc}")
            sys.exit(1)
        except EPDError as exc:
            console.print(f"[red]❌ EPD 错误: {exc}")
            sys.exit(1)

    asyncio.run(_scan())


@epd_group.command(name="drivers")
def epd_drivers():
    """列出支持的墨水屏驱动型号"""
    try:
        from bus_arrival_board.epd import DRIVER_NAMES
    except ImportError as exc:
        console.print(f"[red]❌ EPD 功能不可用: {exc}")
        console.print("[yellow]请安装可选依赖: pip install bus-arrival-board[epd]")
        sys.exit(1)

    table = Table(title="支持的墨水屏驱动型号")
    table.add_column("编号", style="cyan", justify="right")
    table.add_column("型号描述", style="green")

    for driver, name in DRIVER_NAMES.items():
        table.add_row(str(driver.value), name)

    console.print(table)
    console.print("\n[dim]使用方法: epd update --driver <编号> ...")


@epd_group.command(name="preview")
@click.option("--config", required=True, type=click.Path(exists=True), help="配置文件路径")
@click.option("--output", default="/tmp/preview.png", help="输出 PNG 路径，默认 /tmp/preview.png")
@click.option("--width", default=400, help="图像宽度，默认 400")
@click.option("--height", default=300, help="图像高度，默认 300")
def epd_preview(config: str, output: str, width: int, height: int):
    """预览渲染效果（不连接硬件，仅生成 PNG）"""
    try:
        from bus_arrival_board.config import load_config
        from bus_arrival_board.epd import BusDisplayRenderer
        from bus_arrival_board.monitor import BusMonitor
    except ImportError as exc:
        console.print(f"[red]❌ EPD 功能不可用: {exc}")
        console.print("[yellow]请安装可选依赖: pip install bus-arrival-board[epd]")
        sys.exit(1)

    try:
        # 加载配置
        with console.status("[bold green]加载配置..."):
            cfg = load_config(config)
            monitor = BusMonitor(cfg)
            monitor.resolve_targets()

        # 查询实时数据
        with console.status("[bold green]查询实时数据..."):
            results = list(monitor.poll_once())
            if not results:
                console.print("[red]❌ 查询失败，无法获取实时数据")
                sys.exit(1)

            target, result = results[0]

        # 渲染图像
        with console.status("[bold green]渲染图像..."):
            renderer = BusDisplayRenderer(width=width, height=height, mode="1")
            img = renderer.render(result, target)

        # 保存文件
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)

        console.print(f"[green]✓ 预览已生成: {output_path}")
        console.print(f"[dim]尺寸: {img.width}x{img.height} | 模式: {img.mode}")

    except Exception as exc:
        console.print(f"[red]❌ 预览失败: {exc}")
        sys.exit(1)


@epd_group.command(name="update")
@click.option("--config", required=True, type=click.Path(exists=True), help="配置文件路径")
@click.option("--device", required=True, help="设备名称或 MAC 地址，如 NRF_EPD_1234")
@click.option("--driver", default=0, help="驱动型号编号，默认 0（4.2寸黑白 UC8176）")
@click.option("--pins", default=None, help="引脚映射 HEX 字符串，如 0508090A0B0C0D（可选）")
@click.option("--width", default=400, help="图像宽度，默认 400")
@click.option("--height", default=300, help="图像高度，默认 300")
@click.option("--loop", is_flag=True, help="循环模式：持续自动刷新")
@click.option("--interval", default=300, help="循环刷新间隔（秒），默认 300（5分钟）")
def epd_update(
    config: str,
    device: str,
    driver: int,
    pins: str,
    width: int,
    height: int,
    loop: bool,
    interval: int,
):
    """连接墨水屏并推送实时公交信息"""
    import asyncio

    try:
        from bus_arrival_board.config import load_config
        from bus_arrival_board.epd import (
            BusDisplayRenderer,
            EPDClient,
            EPDConnectionError,
            EPDError,
            EPDUpdater,
        )
    except ImportError as exc:
        console.print(f"[red]❌ EPD 功能不可用: {exc}")
        console.print("[yellow]请安装可选依赖: pip install bus-arrival-board[epd]")
        sys.exit(1)

    async def _update():
        epd_client = None
        try:
            # 1. 加载配置
            with console.status("[bold green]加载配置..."):
                cfg = load_config(config)

            # 2. 连接设备
            console.print(f"[cyan]正在连接到 {device}...")
            epd_client = EPDClient()
            await epd_client.connect(device)
            console.print(f"[green]✓ 已连接（固件版本: {epd_client.firmware_version or '未知'}）")

            # 3. 设置引脚（可选）
            if pins:
                console.print(f"[cyan]设置引脚映射: {pins}")
                await epd_client.set_pins(pins)

            # 4. 初始化驱动
            console.print(f"[cyan]初始化驱动（型号 {driver}）...")
            await epd_client.init(driver)
            console.print("[green]✓ 驱动已初始化")

            # 5. 创建渲染器和更新器
            renderer = BusDisplayRenderer(width=width, height=height, mode="1")
            updater = EPDUpdater(cfg, epd_client, renderer)

            # 6. 执行更新
            if loop:
                console.print(
                    f"[green]✓ 进入循环模式（刷新间隔 {interval}秒）\n[dim]按 Ctrl+C 停止\n"
                )
                try:
                    await updater.run_loop(interval_seconds=interval)
                except KeyboardInterrupt:
                    console.print("\n[yellow]收到停止信号，正在退出...")
                    updater.stop()

                # 打印统计
                stats = updater.get_stats()
                console.print("\n[bold cyan]更新统计:")
                console.print(f"  总计: {stats.total_updates}")
                console.print(f"  成功: {stats.successful_updates}")
                console.print(f"  失败: {stats.failed_updates}")
                if stats.last_update_time:
                    console.print(f"  最后更新: {stats.last_update_time.strftime('%H:%M:%S')}")
            else:
                console.print("[cyan]执行单次更新...")
                success = await updater.update_once()
                if success:
                    console.print("[green]✓ 更新成功")
                else:
                    console.print("[red]❌ 更新失败")
                    sys.exit(1)

        except EPDConnectionError as exc:
            console.print(f"[red]❌ 连接失败: {exc}")
            sys.exit(1)
        except EPDError as exc:
            console.print(f"[red]❌ EPD 错误: {exc}")
            sys.exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]用户中断")
        except Exception as exc:
            console.print(f"[red]❌ 更新失败: {exc}")
            sys.exit(1)
        finally:
            # 清理连接
            if epd_client is not None and epd_client.is_connected:
                try:
                    await epd_client.disconnect()
                    console.print("[dim]已断开连接")
                except Exception:
                    pass

    asyncio.run(_update())


if __name__ == "__main__":
    main()
