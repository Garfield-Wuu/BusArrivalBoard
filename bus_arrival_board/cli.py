"""
命令行工具入口
"""
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel

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
                lng=target.lng
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
                    lng=target.lng
                )
                
                console.clear()
                _display_result(result, line_obj, target)
                console.print(f"\n[dim]下次刷新: {interval}秒后 | {datetime.now().strftime('%H:%M:%S')}")
                
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
                city.city_id,
                city.name,
                city.pinyin or "-",
                "✓" if city.support_subway else ""
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
        
        table.add_row(
            str(i),
            bus.bus_id,
            f"第{bus.order}站",
            eta_text,
            bus.crowd_level
        )
    
    console.print(table)
    console.print(f"\n[dim]数据源: {'GPS实时' if result.real_data else '时刻表估算'}")


if __name__ == "__main__":
    main()
