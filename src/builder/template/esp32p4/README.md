# ESP32-P4 firmware template scaffold (T-301)

Minimal placeholder for BSP-integrated firmware skeleton.
Full BSP sources are not vendored here — clone [esp-bsp](https://github.com/espressif/esp-bsp)
and use the Waveshare ESP32-P4 LCD example as the integration base.

## Usage

1. Clone esp-bsp alongside this repo.
2. Copy or symlink BSP component paths per esp-bsp documentation.
3. Generate `board_config.h` via `board_profile_mapper.py` before building.
4. Set target: `idf.py set-target esp32p4`

`board_config.h.in` in the parent `template/` directory supplies macro placeholders
filled by the Python mapper.
