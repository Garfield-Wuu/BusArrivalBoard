idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        epd_driver
        http_frame_client
        wifi_provisioning
        power_management
        nvs_flash
        driver
)
