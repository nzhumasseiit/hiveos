#!/usr/bin/env python3
"""HiveOS Pi gateway: receive HivePacket v1, POST to /api/readings.

Two transports, picked with HIVEOS_TRANSPORT:
  uart  (default) — a receiver ESP32 owns the nRF24 radio and forwards each
                    packet to the Pi over serial, one line per packet: either
                    hex-encoded raw HivePacket ("01A2...") or a JSON object
                    ({"seq": 7, "temp_c": 34.2, ...}).
  nrf24           — the nRF24 radio is wired to the Pi's SPI directly.

Buffers to disk when the network is down, flushes when it comes back —
readings are never lost. See SPEC.md for the packet format.

Usage:
    HIVEOS_URL=https://beelive.onrender.com \
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

# --- config (env vars) -------------------------------------------------------
URL        = os.environ.get("HIVEOS_URL", "").rstrip("/")
API_KEY    = os.environ.get("HIVEOS_API_KEY", "")
HIVE_ID    = os.environ.get("HIVEOS_HIVE_ID", "hive-1")
DEVICE_ID  = os.environ.get("HIVEOS_DEVICE_ID", "esp32-1")
TRANSPORT  = os.environ.get("HIVEOS_TRANSPORT", "uart")   # uart | nrf24
# uart transport
SERIAL_PORT = os.environ.get("HIVEOS_SERIAL_PORT", "/dev/serial0")
BAUD        = int(os.environ.get("HIVEOS_BAUD", "115200"))
# nrf24 transport
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


# Every field the API accepts; JSON lines may carry any of these directly.
API_FIELDS = {name for _, name, _ in FIELDS} | {"vibration"}


def parse_line(line: str):
    """One UART line -> (seq, readings dict) or (None, None) if invalid.

    seq is None (with valid readings) when the line is JSON without a "seq"
    key — loss tracking is skipped for those.
    """
    line = line.strip()
    if not line:
        return None, None
    if line.startswith("{"):
        try:
            data = json.loads(line)
        except ValueError:
            return None, None
        if not isinstance(data, dict):
            return None, None
        seq = data.get("seq")
        readings = {k: float(v) for k, v in data.items()
                    if k in API_FIELDS and isinstance(v, (int, float))}
        if not readings:
            return None, None
        return (int(seq) % 256 if isinstance(seq, (int, float)) else None), readings
    try:
        return decode(bytes.fromhex(line))
    except ValueError:
        return None, None


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
        "protocol": "uart" if TRANSPORT == "uart" else "nrf24",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "readings": readings,
    }


# --- transports ----------------------------------------------------------------
def open_uart():
    """Returns a poll() -> (seq, readings) | None closure reading serial lines."""
    try:
        import serial
    except ImportError:
        sys.exit("pyserial is not installed — run: pip install pyserial")
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0.2)
    except serial.SerialException as exc:
        sys.exit(f"Cannot open {SERIAL_PORT}: {exc}\n"
                 "On GPIO pins: enable the serial port via raspi-config "
                 "(login shell: No, serial hardware: Yes). Over USB: try /dev/ttyUSB0.")
    print(f"reading {SERIAL_PORT} @ {BAUD} baud")

    def poll():
        line = ser.readline()  # returns b"" after the 0.2s timeout
        if not line.strip():
            return None
        seq, readings = parse_line(line.decode("ascii", errors="replace"))
        if not readings:  # invalid packet, or one with an empty field mask
            print(f"[skip] bad line: {line[:60]!r}")
            return None
        return seq, readings

    return poll


def open_nrf24():
    """Returns a poll() -> (seq, readings) | None closure reading the radio."""
    try:
        from pyrf24 import RF24, RF24_250KBPS, RF24_PA_MAX
    except ImportError:
        sys.exit("pyrf24 is not installed — run: pip install pyrf24")
    radio = RF24(CE_PIN, CSN_PIN)
    if not radio.begin():
        sys.exit("nRF24 not responding — check wiring and SPI")
    radio.setDataRate(RF24_250KBPS)
    radio.setPALevel(RF24_PA_MAX)
    radio.setChannel(CHANNEL)
    radio.open_rx_pipe(1, PIPE_ADDR)
    radio.payload_size = 18
    radio.listen = True
    print(f"listening on channel {CHANNEL}, pipe {PIPE_ADDR!r}")

    def poll():
        if not radio.available():
            time.sleep(0.05)
            return None
        seq, readings = decode(bytes(radio.read(radio.payload_size)))
        if not readings:  # invalid packet, or one with an empty field mask
            print("[skip] bad packet")
            return None
        return seq, readings

    return poll


# --- main loop ----------------------------------------------------------------
def main():
    if not URL or not API_KEY:
        sys.exit("Set HIVEOS_URL and HIVEOS_API_KEY environment variables")
    if TRANSPORT not in ("uart", "nrf24"):
        sys.exit(f"Unknown HIVEOS_TRANSPORT: {TRANSPORT!r} (use uart or nrf24)")

    poll = open_uart() if TRANSPORT == "uart" else open_nrf24()

    buf = buffer_init()
    last_seq = None
    lost = received = 0
    last_flush = 0.0
    print(f"forwarding to {URL}/api/readings as {HIVE_ID}/{DEVICE_ID}")

    while True:
        packet = poll()
        if packet is not None:
            seq, readings = packet
            received += 1
            if seq is not None:
                if last_seq is not None:
                    gap = (seq - last_seq - 1) % 256
                    if gap:
                        lost += gap
                last_seq = seq

            print(f"seq={seq} loss={lost}/{lost + received} {readings}")
            body = make_body(readings)
            if not post_reading(body):
                buffer_put(buf, body)

        now = time.monotonic()
        if now - last_flush > FLUSH_EVERY:
            last_flush = now
            n = buffer_flush(buf)
            if n:
                print(f"[flush] sent {n} buffered readings")


if __name__ == "__main__":
    main()
