# BusArrivalBoard ESP32 固件 — 顶层构建配置
#
# 需要 ESP-IDF v5.1 或更高版本。
#
# 构建:
#   idf.py set-target esp32s3
#   idf.py menuconfig      # 配置 WiFi 与服务器地址
#   idf.py build
#   idf.py -p /dev/ttyUSB0 flash monitor

cmake_minimum_required(VERSION 3.16)

# components/ 会被 ESP-IDF 自动扫描，无需显式声明
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(bus_arrival_display)
