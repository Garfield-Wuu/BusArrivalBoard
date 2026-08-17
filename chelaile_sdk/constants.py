"""
车来了 API 常量定义
"""

# API 基础配置
BASE_URL = "https://web.chelaile.net.cn/api"
BASE_DOMAIN = "https://web.chelaile.net.cn"

# 默认请求参数
DEFAULT_PARAMS = {
    "s": "h5",
    "wxs": "wx_app",
    "sign": "1",
    "h5RealData": "1",
    "v": "3.11.28",
    "src": "weixinapp_cx",
    "ctm_mp": "mp_wx",
    "vc": "2",
    "favoriteGray": "1",
    "gpstype": "wgs",
    "geo_type": "wgs",
    "scene": "1256",
}

# HTTP 请求头（指纹识别，不可随意修改）
REQUEST_HEADERS = {
    "Host": "web.chelaile.net.cn",
    "Connection": "keep-alive",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/132.0.0.0 Safari/537.36 "
        "MicroMessenger/7.0.20.1781(0x6700143B) "
        "NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF "
        "WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf254160a) "
        "XWEB/18055"
    ),
    "xweb_xhr": "1",
    "Content-Type": "text",
    "Accept": "*/*",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://servicewechat.com/wx71d589ea01ce3321/814/page-frame.html",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# API 端点
ENDPOINTS = {
    "search": "/bus/query!nSearch.action",
    "line_detail": "/bus/line!encryptedLineDetail.action",
    "line_realtime": "/bus/line!encryptedBusDetail.action",
    "city_list": "/wwd/ncitylist",
}

# 超时配置（秒）
REQUEST_TIMEOUT = 15
DEFAULT_REFRESH_INTERVAL = 60
