# HQPlayer Home Assistant Integration (HACS)

> **Note / 注意:** This integration is currently **under active development (WIP / 開発中)**. Breaking changes or protocol adjustments may occur.

Home Assistant custom integration for controlling **HQPlayer** via the **HQPlayer Control API (TCP 4321 / XML-over-TCP)**.

## Features
- **Dynamic option discovery**: Filters (1x / Nx), Shaper/Modulator, Output Mode (PCM / SDM), Sample Rate, and Matrix Profiles are fetched dynamically from HQPlayer.
- **Automatic sync**: `SelectEntity` options and current selections automatically track changes made externally or when switching output modes / reconnecting.
- **Entities**:
  - `select`: Filter 1x, Filter Nx, Shaper / Modulator, Output Mode, Sample Rate, Matrix Profile
  - `number`: Volume (dB)
  - `sensor`: Playback State, Input Sample Rate, Output Sample Rate, Input Format, Output Format
  - `button`: Refresh

## Installation (HACS)
1. Add this repository as a custom repository in HACS (Category: **Integration**).
2. Install **HQPlayer** and restart Home Assistant.
3. Go to **Settings -> Devices & Services -> Add Integration -> HQPlayer** and enter your HQPlayer host and port (`4321`).
