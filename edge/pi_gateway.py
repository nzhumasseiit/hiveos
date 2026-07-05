#!/usr/bin/env python3
"""HiveOS Pi gateway: receive HivePacket v1 over nRF24, POST to /api/readings.

Buffers to disk when the network is down, flushes when it comes back —
readings are never lost. See SPEC.md for the packet format.

Usage:
    HIVEOS_URL=https://your-app.onrender.com \
    HIVEOS_API_KEY=your-ingest-key \
    python3 pi_gateway.py
"""
import json
import os
import sqlite3
import struct
import sys
import time
from datetime import datetime, timezone

import requests
from pyrf24 import RF24, RF24_250KBPS, RF24_PA_MAX

# --- config (env vars) -------------------------------------------------------
URL        = os.environ.get("HIVEOS_URL", "").rstrip("/")
API_KEY    = os.environ.get("HIVEOS_API_KEY", "")
HIVE_ID    = os.environ.get("HIVEOS_HIVE_ID", "hive-1")
DEVICE_ID  = os.environ.get("HIVEOS_DEVICE_ID", "esp32-1")
CE_PIN     = int(os.environ.get("HIVEOS_CE_PIN", "22"))   # GPIO22
CSN_PIN    = int(os.environ.get("HIVEOS_CSN_PIN", "0"))   # SPI CE0
CHANNEL    = int(os.environ.get("HIVEOS_CHANNEL", "76"))
PIPE_ADDR  = os.environ.get("HIVEOS_PIPE", "hive1").encode()
BUFFER_DB  = os.environ.get("HIVEOS_BUFFER", os.path.expanduser("~/hiveos_buffer.db"))
FLUSH_EVERY = 30  # seconds between buffer flush attempts

# --- packet decoding (SPEC.md, HivePacket v1) --------------------------------
FMT = "<BBBhHHHHHBBB"  # 18 bytes, little-endian
FIELDS = [  # (bit, api field, decoder)
    (0, "temp_c",      lambda v: v / 100),
    (1, "humidity",    lambda v: v / 100),
    (2, "pressure",    lambda v: v / 10),
    (3, "alcohol_ppm", float),
    (4, "methane_ppm", float),   # co2 raw ADC mapped to methane_ppm
    (5, "weight_kg",   lambda v: v / 10),
    (6, "noise_db",    float),
    (7, "battery",     float),
]


def decode(payload: bytes):
    """32-byte nRF payload -> (seq, readings dict) or (None, None) if invalid."""
    if len(payload) < 18 or payload[0] != 1:
        return None, None
    (_, seq, valid, t, h, pr, alc, co2,
     w, nz, bat, vib) = struct.unpack(FMT, payload[:18])
    raw = [t, h, pr, alc, co2, w, nz, bat]
    readings = {name: fn(raw[i])
                for i, (bit, name, fn) in enumerate(FIELDS)
                if valid & (1 << bit)}
    return seq, readings


# --- disk buffer: survive network dropouts -----------------------------------
def buffer_init():
    conn = sqlite3.connect(BUFFER_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pending ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  body TEXT NOT NULL)"
    )
    conn.commit()
    return conn


def buffer_put(conn, body: dict):
    conn.execute("INSERT INTO pending (body) VALUES (?)", (json.dumps(body),))
    conn.commit()


def buffer_flush(conn) -> int:
    """Try to send everything pending. Returns how many were sent."""
    rows = conn.execute("SELECT id, body FROM pending ORDER BY id LIMIT 500").fetchall()
    sent = 0
    for row_id, body in rows:
        if not post_reading(json.loads(body)):
            break  # network still down, keep the rest for later
        conn.execute("DELETE FROM pending WHERE id = ?", (row_id,))
        conn.commit()
        sent += 1
    return sent


# --- cloud -------------------------------------------------------------------
def post_reading(body: dict) -> bool:
    try:
        r = requests.post(
            f"{URL}/api/readings",
            headers={"X-API-Key": API_KEY},
            json=body,
            timeout=10,
        )
        if r.status_code == 200:
            return True
        # 4xx means the payload is wrong, not the network — don't retry forever
        if 400 <= r.status_code < 500:
            print(f"[drop] server rejected ({r.status_code}): {r.text[:120]}")
            return True
        print(f"[retry-later] server error {r.status_code}")
        return False
    except requests.RequestException as exc:
        print(f"[offline] {exc.__class__.__name__}")
        return False


def make_body(readings: dict) -> dict:
    return {
        "hive_id": HIVE_ID,
        "device_id": DEVICE_ID,
        "sensor_type": "environment",
        "protocol": "nrf24",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "readings": readings,
    }


# --- main loop ----------------------------------------------------------------
def main():
    if not URL or not API_KEY:
        sys.exit("Set HIVEOS_URL and HIVEOS_API_KEY environment variables")

    radio = RF24(CE_PIN, CSN_PIN)
    if not radio.begin():
        sys.exit("nRF24 not responding — check wiring and SPI")
    radio.setDataRate(RF24_250KBPS)
    radio.setPALevel(RF24_PA_MAX)
    radio.setChannel(CHANNEL)
    radio.open_rx_pipe(1, PIPE_ADDR)
    radio.payload_size = 18
    radio.listen = True

    buf = buffer_init()
    last_seq = None
    lost = received = 0
    last_flush = 0.0
    print(f"listening on channel {CHANNEL}, pipe {PIPE_ADDR!r} -> {URL}/api/readings")

    while True:
        if radio.available():
            payload = radio.read(radio.payload_size)
            seq, readings = decode(bytes(payload))
            if seq is None:
                print("[skip] bad packet")
                continue

            received += 1
            if last_seq is not None:
                gap = (seq - last_seq - 1) % 256
                if gap:
                    lost += gap
            last_seq = seq

            print(f"seq={seq} loss={lost}/{lost + received} {readings}")
            if readings:
                body = make_body(readings)
                if not post_reading(body):
                    buffer_put(buf, body)

        now = time.monotonic()
        if now - last_flush > FLUSH_EVERY:
            last_flush = now
            n = buffer_flush(buf)
            if n:
                print(f"[flush] sent {n} buffered readings")

        time.sleep(0.05)


if __name__ == "__main__":
    main()
