# Pi gateway

Приёмник nRF24 на Raspberry Pi: слушает пакеты HivePacket v1 (см. [SPEC.md](../SPEC.md)),
декодирует и постит в облако на `/api/readings`. При отсутствии сети буферизует
показания в SQLite на SD-карте и дошлёт, когда сеть появится.

## Подключение nRF24 к Pi (SPI)

| nRF24 | Pi (физический пин) |
|-------|---------------------|
| VCC   | 3.3V (pin 1) — НЕ 5V! |
| GND   | GND (pin 6)         |
| CE    | GPIO22 (pin 15)     |
| CSN   | CE0 (pin 24)        |
| SCK   | SCLK (pin 23)       |
| MOSI  | MOSI (pin 19)       |
| MISO  | MISO (pin 21)       |

Плюс конденсатор 10–100 мкФ между VCC и GND у модуля.
Включить SPI: `sudo raspi-config` → Interface Options → SPI → Enable.

## Установка

```bash
sudo apt install python3-pip
pip3 install pyrf24 requests
```

## Запуск

```bash
export HIVEOS_URL=https://<your-app>.onrender.com
export HIVEOS_API_KEY=<INGEST_API_KEY>
export HIVEOS_HIVE_ID=hive-1
python3 pi_gateway.py
```

Все настройки — через переменные окружения:

| Переменная | Default | Что это |
|---|---|---|
| `HIVEOS_URL` | — (обязательно) | URL бэкенда на Render |
| `HIVEOS_API_KEY` | — (обязательно) | значение `INGEST_API_KEY` бэкенда |
| `HIVEOS_HIVE_ID` | `hive-1` | имя улья (создастся при первом POST) |
| `HIVEOS_DEVICE_ID` | `esp32-1` | id устройства |
| `HIVEOS_CE_PIN` | `22` | GPIO для CE |
| `HIVEOS_CSN_PIN` | `0` | SPI CE0 |
| `HIVEOS_CHANNEL` | `76` | канал nRF (одинаковый с ESP32!) |
| `HIVEOS_PIPE` | `hive1` | адрес пайпа (одинаковый с ESP32!) |
| `HIVEOS_BUFFER` | `~/hiveos_buffer.db` | файл офлайн-буфера |

## Автозапуск (systemd)

`/etc/systemd/system/hiveos-gateway.service`:

```ini
[Unit]
Description=HiveOS nRF24 gateway
After=network-online.target

[Service]
User=pi
Environment=HIVEOS_URL=https://<your-app>.onrender.com
Environment=HIVEOS_API_KEY=<INGEST_API_KEY>
ExecStart=/usr/bin/python3 /home/pi/hiveos/edge/pi_gateway.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now hiveos-gateway
journalctl -u hiveos-gateway -f   # смотреть логи
```

## Что видно в логах

- `seq=42 loss=0/43 {'temp_c': 34.2, ...}` — пакет принят; `loss` = потери радиоканала
- `[offline] ConnectionError` — сети нет, показание ушло в буфер
- `[flush] sent 12 buffered readings` — сеть вернулась, буфер дослан
- `[drop] server rejected (400)` — бэкенд отверг payload (смотри текст ошибки)
