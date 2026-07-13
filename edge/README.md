# Pi gateway

Шлюз на Raspberry Pi: принимает показания HivePacket v1 (см. [SPEC.md](../SPEC.md)),
декодирует и постит в облако на `/api/readings`. При отсутствии сети буферизует
показания в SQLite на SD-карте и дошлёт, когда сеть появится.

Два транспорта (`HIVEOS_TRANSPORT`):

- **`uart`** (default) — радио nRF24 висит на приёмном ESP32, а тот пересылает
  пакеты в Pi по UART. Схема: улей → nRF24 → ESP32 → UART → Pi → Altel 5G → облако.
- **`nrf24`** — модуль nRF24 подключён напрямую к SPI самого Pi.

## Вариант A: UART (ESP32-приёмник → Pi)

### Подключение

| ESP32 | Pi (физический пин) |
|-------|---------------------|
| TX (GPIO17) | RXD / GPIO15 (pin 10) |
| RX (GPIO16) | TXD / GPIO14 (pin 8) |
| GND   | GND (pin 6) — общая земля обязательна |

ESP32 — 3.3V логика, так что уровни совместимы напрямую. Если ESP32 подключён
к Pi **по USB-кабелю**, пины не нужны — порт будет `/dev/ttyUSB0` (или `/dev/ttyACM0`).

Для GPIO-пинов включить UART: `sudo raspi-config` → Interface Options →
Serial Port → login shell **No**, serial hardware **Yes**, перезагрузка.
Порт после этого — `/dev/serial0`.

### Протокол по UART

Одна строка (`\n` в конце) на один пакет, ESP32 может слать любой из форматов —
скрипт понимает оба и молча пропускает мусор (boot-логи ESP32 и т.п.):

1. **Hex сырого HivePacket** — прошивке не нужно ничего декодировать:

   ```cpp
   // в прошивке приёмного ESP32, после radio.read(buf, 18):
   for (int i = 0; i < 18; i++) Serial.printf("%02X", buf[i]);
   Serial.println();
   ```

2. **JSON-объект** — если прошивка декодирует сама:

   ```json
   {"seq": 42, "temp_c": 34.2, "humidity": 61.5, "weight_kg": 41.3}
   ```

   Поля: `temp_c`, `humidity`, `pressure`, `alcohol_ppm`, `methane_ppm`,
   `noise_db`, `weight_kg`, `battery`, `vibration`; `seq` (0-255) опционален —
   с ним считаются потери радиоканала.

### Установка и запуск

```bash
sudo apt install python3-pip
pip3 install pyserial requests

export HIVEOS_URL=https://beelive.onrender.com
export HIVEOS_API_KEY=<INGEST_API_KEY>
export HIVEOS_HIVE_ID=hive-1
python3 pi_gateway.py
```

Быстрая проверка без ESP32 — вручную вбросить строку в порт с другого терминала:

```bash
echo '{"temp_c": 25.0, "humidity": 50.0}' > /dev/serial0
```

## Вариант B: nRF24 напрямую к Pi (SPI)

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

```bash
pip3 install pyrf24 requests
HIVEOS_TRANSPORT=nrf24 python3 pi_gateway.py
```

## Переменные окружения

| Переменная | Default | Что это |
|---|---|---|
| `HIVEOS_URL` | — (обязательно) | URL бэкенда на Render |
| `HIVEOS_API_KEY` | — (обязательно) | значение `INGEST_API_KEY` бэкенда |
| `HIVEOS_HIVE_ID` | `hive-1` | имя улья (создастся при первом POST) |
| `HIVEOS_DEVICE_ID` | `esp32-1` | id устройства |
| `HIVEOS_TRANSPORT` | `uart` | `uart` или `nrf24` |
| `HIVEOS_SERIAL_PORT` | `/dev/serial0` | uart: порт (`/dev/ttyUSB0` для USB) |
| `HIVEOS_BAUD` | `115200` | uart: скорость (та же, что в прошивке!) |
| `HIVEOS_CE_PIN` | `22` | nrf24: GPIO для CE |
| `HIVEOS_CSN_PIN` | `0` | nrf24: SPI CE0 |
| `HIVEOS_CHANNEL` | `76` | nrf24: канал (одинаковый с ESP32!) |
| `HIVEOS_PIPE` | `hive1` | nrf24: адрес пайпа (одинаковый с ESP32!) |
| `HIVEOS_BUFFER` | `~/hiveos_buffer.db` | файл офлайн-буфера |

## Автозапуск (systemd)

`/etc/systemd/system/hiveos-gateway.service`:

```ini
[Unit]
Description=HiveOS gateway
After=network-online.target

[Service]
User=pi
Environment=HIVEOS_URL=https://beelive.onrender.com
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
- `[skip] bad line: ...` — строка не распозналась (boot-мусор ESP32 — это нормально)
- `[offline] ConnectionError` — сети нет, показание ушло в буфер
- `[flush] sent 12 buffered readings` — сеть вернулась, буфер дослан
- `[drop] server rejected (400)` — бэкенд отверг payload (смотри текст ошибки)
