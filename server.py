"""Stream a RealSense point cloud to any browser on your Wi-Fi.

Run:  sudo $(which python) server.py
Open: http://<this-mac-ip>:8080  (the IP is printed on start)

Tries stream settings from best (USB 3) to lightest (USB 2, depth only)
and uses the first one the camera accepts.
"""
import asyncio
import os
import socket
import struct
import threading

import numpy as np
import pyrealsense2 as rs
from aiohttp import web

STRIDE = 4          # sample every 4th pixel. Use 2 for denser, 8 for lighter.
MIN_Z, MAX_Z = 0.1, 4.0   # meters; points outside are dropped
PORT = 8080

# (width, height, fps, with_color), tried in order
CONFIGS = [
    (640, 480, 30, True),
    (640, 480, 15, True),
    (424, 240, 15, True),
    (424, 240, 6, True),
    (640, 480, 15, False),
    (424, 240, 15, False),
]

frame_id = 0
latest = None
lock = threading.Lock()


def start_pipeline():
    for w, h, fps, with_color in CONFIGS:
        pipe = rs.pipeline()
        cfg = rs.config()
        cfg.enable_stream(rs.stream.depth, w, h, rs.format.z16, fps)
        if with_color:
            cfg.enable_stream(rs.stream.color, w, h, rs.format.rgb8, fps)
        try:
            profile = pipe.start(cfg)
            pipe.wait_for_frames(4000)  # make sure frames actually arrive
            kind = "depth + color" if with_color else "depth only (colored by distance)"
            print(f"Camera started: {w}x{h} @ {fps} fps, {kind}")
            return pipe, profile, with_color
        except Exception as e:
            reason = str(e).strip().splitlines()[-1] if str(e).strip() else "unknown"
            print(f"  {w}x{h}@{fps} color={with_color} failed: {reason}")
            try:
                pipe.stop()
            except Exception:
                pass
    raise RuntimeError("No stream setting worked. Try a USB 3 cable/port and re-plug the camera.")


def distance_colors(z):
    """Blue (near) -> green -> red (far), as uint8 RGB."""
    t = np.clip((z - MIN_Z) / (MAX_Z - MIN_Z), 0, 1)
    r = 255 * np.clip(2 * t - 0.5, 0, 1)
    g = 255 * (1 - np.abs(2 * t - 1))
    b = 255 * np.clip(1 - 2 * t, 0, 1)
    return np.stack([r, g, b], axis=1).astype(np.uint8)


def camera_loop():
    global frame_id, latest
    pipe, profile, with_color = start_pipeline()

    scale = profile.get_device().first_depth_sensor().get_depth_scale()
    intr = profile.get_stream(rs.stream.depth).as_video_stream_profile().get_intrinsics()
    align = rs.align(rs.stream.depth) if with_color else None

    u = np.arange(0, intr.width, STRIDE)
    v = np.arange(0, intr.height, STRIDE)
    uu, vv = np.meshgrid(u, v)
    x_factor = (uu - intr.ppx) / intr.fx
    y_factor = (vv - intr.ppy) / intr.fy

    while True:
        frames = pipe.wait_for_frames()
        if align is not None:
            frames = align.process(frames)
        depth = frames.get_depth_frame()
        if not depth:
            continue
        color = frames.get_color_frame() if with_color else None
        if with_color and not color:
            continue

        z = np.asanyarray(depth.get_data())[::STRIDE, ::STRIDE].astype(np.float32) * scale
        mask = (z > MIN_Z) & (z < MAX_Z)
        zm = z[mask]
        pos_mm = np.stack([x_factor[mask] * zm, y_factor[mask] * zm, zm], axis=1) * 1000.0
        n = zm.shape[0]

        if with_color:
            rgb = np.asanyarray(color.get_data())[::STRIDE, ::STRIDE][mask]
        else:
            rgb = distance_colors(zm)

        payload = (
            struct.pack("<I", n)
            + pos_mm.astype("<i2").tobytes()        # n*3 int16, millimeters
            + np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()  # n*3 uint8
        )
        with lock:
            latest = payload
            frame_id += 1


async def index(request):
    return web.FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


async def ws_handler(request):
    ws = web.WebSocketResponse(max_msg_size=0)
    await ws.prepare(request)
    last = -1
    try:
        while not ws.closed:
            with lock:
                fid, data = frame_id, latest
            if data is not None and fid != last:
                await ws.send_bytes(data)
                last = fid
            await asyncio.sleep(0.02)
    except (ConnectionResetError, asyncio.CancelledError):
        pass
    return ws


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        s.close()


if __name__ == "__main__":
    threading.Thread(target=camera_loop, daemon=True).start()
    app = web.Application()
    app.add_routes([web.get("/", index), web.get("/ws", ws_handler)])
    print(f"\nOpen on any device on your Wi-Fi:  http://{local_ip()}:{PORT}\n")
    web.run_app(app, host="0.0.0.0", port=PORT, print=None)
