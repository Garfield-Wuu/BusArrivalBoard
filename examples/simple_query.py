"""简单使用示例 - 查询深圳M592路实时到站"""
from chelaile_sdk import ChelaiLeClient

# 创建客户端
client = ChelaiLeClient()

# 1. 搜索城市
city = client.search_city("深圳")
print(f"城市: {city.name} (ID: {city.city_id})")

# 2. 搜索线路
lines = client.search_line(city.city_id, "M592")
if not lines:
    print("未找到M592线路")
    exit(1)

line = lines[0]
print(f"线路: {line.name} {line.start_station} → {line.end_station}")

# 3. 获取线路详情（站点列表）
stations = client.get_line_detail(city.city_id, line.line_id)

# 查找目标站点
target_station = None
for station in stations:
    if "安翼嘉寓" in station.name:
        target_station = station
        break

if not target_station:
    print("未找到安翼嘉寓站")
    exit(1)

print(f"目标站: {target_station.name} (第{target_station.order}站)")

# 4. 获取实时到站信息
result = client.get_realtime_buses(
    city_id=city.city_id,
    line_id=line.line_id,
    station_id=target_station.station_id,
    target_order=target_station.order,
    lat=target_station.lat,
    lng=target_station.lng
)

print(f"\n实时数据: {'有GPS' if result.real_data else '时刻表'}")
print(f"后方共 {len(result.buses)} 辆公交:\n")

for i, bus in enumerate(result.buses, 1):
    if bus.eta:
        eta_text = f"{bus.eta_minutes}分钟 (预计 {bus.eta.display_time})"
    else:
        eta_text = "暂无预测"
    
    print(f"🚌 {i}. {bus.bus_id}")
    print(f"   位置: 第{bus.order}站 | 拥挤度: {bus.crowd_level}")
    print(f"   预计到达: {eta_text}\n")
