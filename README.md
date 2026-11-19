# RealSense Hologram

Stream a live 3D point cloud from an Intel® RealSense™ depth camera to any browser on your local network — phone, tablet or laptop. No app install needed on the viewing device.

The Python server reads depth (and color, when available) frames from the camera, converts them to a compact binary point cloud, and pushes them over a WebSocket. The browser renders the points in real time with [Three.js](https://threejs.org/), with orbit, zoom and pan controls.

## Features

- **Live 3D point cloud** in the browser, viewable from any device on the same Wi-Fi
- **Automatic stream fallback** — tries settings from best (640×480 @ 30 fps, depth + color, USB 3) down to lightest (424×240, depth only, USB 2) and uses the first one the camera accepts
- **Distance coloring** when no color stream is available (blue = near → green → red = far)
- **Compact binary protocol** — positions as `int16` millimeters, colors as `uint8` RGB
- **Interactive viewer** — drag to orbit, scroll to zoom, right-drag to pan, with a live FPS / point count HUD
- **Auto-reconnect** if the connection drops

## Requirements

- An Intel RealSense depth camera (e.g. D415 / D435 / D455)
- Python 3.8+
- macOS or Linux (on macOS, `pyrealsense2` usually needs `sudo` for USB access)
- A USB 3 cable and port is recommended for depth + color at higher frame rates

## Installation

```bash
git clone https://github.com/<your-username>/realsense-hologram.git
cd realsense-hologram
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
sudo $(which python) server.py
```

The server prints the address to open, for example:

```
Camera started: 640x480 @ 30 fps, depth + color

Open on any device on your Wi-Fi:  http://192.168.1.42:8080
```

Open that URL in a browser on any device connected to the same network.

### Controls

| Action      | Input                     |
|-------------|---------------------------|
| Orbit       | Drag / one-finger swipe   |
| Zoom        | Scroll / pinch            |
| Pan         | Right-drag / two-finger drag |

## Configuration

Tweak these constants at the top of [`server.py`](server.py):

| Setting          | Default        | Description                                              |
|------------------|----------------|----------------------------------------------------------|
| `STRIDE`         | `4`            | Sample every Nth pixel. `2` = denser, `8` = lighter      |
| `MIN_Z`, `MAX_Z` | `0.1`, `4.0`   | Depth range in meters; points outside are dropped        |
| `PORT`           | `8080`         | HTTP / WebSocket port                                    |
| `CONFIGS`        | see file       | Stream settings tried in order: `(width, height, fps, with_color)` |

> If you lower `STRIDE`, raise `MAX_POINTS` in [`index.html`](index.html) to match (e.g. `320 * 240 = 76800` for `STRIDE = 2`).

## How it works

```
RealSense camera ──► server.py (pyrealsense2 + NumPy)
                        │  deproject depth pixels → XYZ (mm)
                        │  attach RGB or distance colors
                        ▼
                   WebSocket /ws  (binary frames)
                        ▼
                  index.html (Three.js Points)
```

Each WebSocket message has this layout (little-endian):

| Offset        | Type          | Content                        |
|---------------|---------------|--------------------------------|
| `0`           | `uint32`      | Point count `n`                |
| `4`           | `int16 × 3n`  | X, Y, Z positions in millimeters |
| `4 + 6n`      | `uint8 × 3n`  | R, G, B colors                 |

## Troubleshooting

- **"No stream setting worked"** — re-plug the camera, try a different USB 3 port/cable, and make sure no other app (e.g. RealSense Viewer) is using it.
- **Permission errors on macOS** — run the server with `sudo` as shown above.
- **Page won't load from another device** — confirm both devices are on the same network and that your firewall allows incoming connections on port `8080`.
- **Low frame rate** — increase `STRIDE` or use a USB 3 connection.

## Project structure

```
.
├── server.py          # Camera capture + HTTP/WebSocket server
├── index.html         # Three.js point cloud viewer
├── requirements.txt   # Python dependencies
└── README.md
```
