# M5Stack CoreS3 firmware template scaffold (T-301)

Minimal placeholder for CoreS3 (ESP32-S3) auxiliary target.
Refer to M5Stack official BSP / esp-bsp for full LCD driver integration.

## Usage

1. Clone esp-bsp or M5Stack BSP examples.
2. Generate `board_config.h` via `board_profile_mapper.py` with `cores3` profile.
3. Set target: `idf.py set-target esp32s3`

This target is cut by default (T-006/T-504); scaffold exists for multi-board header branching only.
