# HivePacket v1 — спека радиопакета nRF24

Формат данных между ESP32 (датчики на улье) и Raspberry Pi (шлюз в облако).

```
ESP32 + датчики ──nRF24 (binary struct, 18 байт)──> Pi ──HTTP (JSON)──> облако
```

**Канал:** nRF24L01+PA+LNA, 250 kbps, PA_MAX, payload 18 байт (лимит чипа — 32).

⚠️ **Обязательно:** конденсатор 10–100 мкФ между VCC и GND прямо у каждого модуля nRF.
Без него PA+LNA-версия глючит при передаче — самая частая причина «нестабильного nRF».

---

## 1. Раскладка пакета (little-endian, 18 байт)

| Байты | Поле        | Тип    | Кодирование                          |
|-------|-------------|--------|--------------------------------------|
| 0     | `version`   | uint8  | всегда `0x01`                        |
| 1     | `seq`       | uint8  | счётчик пакетов 0–255 (переполнение — норм) |
| 2     | `valid`     | uint8  | битовая маска валидности полей       |
| 3–4   | `temp_c`    | int16  | °C × 100 (34.25 °C → `3425`)         |
| 5–6   | `humidity`  | uint16 | % × 100                              |
| 7–8   | `pressure`  | uint16 | гПа × 10                             |
| 9–10  | `alcohol`   | uint16 | raw ADC 0–4095                       |
| 11–12 | `co2`       | uint16 | raw ADC 0–4095                       |
| 13–14 | `weight`    | uint16 | кг × 10                              |
| 15    | `noise`     | uint8  | dB                                   |
| 16    | `battery`   | uint8  | %                                    |
| 17    | `vibration` | uint8  | 0/1                                  |

## 2. Маска `valid`

Бит = 1 ⟺ датчик реально ответил в этом цикле опроса.

```
bit 0 = temp   bit 1 = humidity  bit 2 = pressure  bit 3 = alcohol
bit 4 = co2    bit 5 = weight    bit 6 = noise     bit 7 = battery
```

Правила:
- DS18B20 вернул −127 (`DEVICE_DISCONNECTED_C`) → бит 0 не ставить.
- DHT вернул `nan` → бит 1 не ставить.
- HX711 не `is_ready()` → бит 5 не ставить.
- **Никогда не слать мусорные значения с установленным битом.**
- У `vibration` бита нет — шлётся всегда (0 по умолчанию).

## 3. ESP32 — отправка (C/Arduino)

```c
typedef struct __attribute__((packed)) {
  uint8_t  version;    // 0x01
  uint8_t  seq;
  uint8_t  valid;
  int16_t  temp_c;     // x100
  uint16_t humidity;   // x100
  uint16_t pressure;   // x10 hPa
  uint16_t alcohol;    // raw ADC
  uint16_t co2;        // raw ADC
  uint16_t weight;     // x10 kg
  uint8_t  noise;      // dB
  uint8_t  battery;    // %
  uint8_t  vibration;
} HivePacket;          // = 18 bytes, проверь sizeof!

static uint8_t seq = 0;

void sendReadings() {
  HivePacket p = {0};
  p.version = 1;
  p.seq = seq++;

  float t = sensors.getTempCByIndex(0);
  if (t != DEVICE_DISCONNECTED_C) { p.temp_c = t * 100; p.valid |= 1 << 0; }

  float h = dht.readHumidity();
  if (!isnan(h)) { p.humidity = h * 100; p.valid |= 1 << 1; }

  // pressure, если BME280 подключён:
  // p.pressure = bme.readPressure() / 10; p.valid |= 1 << 2;

  p.alcohol = analogRead(MQ3_PIN);   p.valid |= 1 << 3;
  p.co2     = analogRead(MQ135_PIN); p.valid |= 1 << 4;

  if (scale.is_ready()) {
    float w = scale.get_units(5);
    if (w >= 0 && w < 500) { p.weight = w * 10; p.valid |= 1 << 5; }
  }

  radio.write(&p, sizeof(p));
}
```

### Настройка радио (обе стороны одинаково)

```c
radio.begin();
radio.setDataRate(RF24_250KBPS);   // ниже скорость — дальше добивает
radio.setPALevel(RF24_PA_MAX);
radio.setChannel(76);              // один канал на обеих сторонах
radio.openWritingPipe((const uint8_t*)"hive1");
```

## 4. Чеклист совместимости

- [ ] `sizeof(HivePacket) == 18` на ESP32 (иначе проверить `__attribute__((packed))`)
- [ ] Одинаковые канал, дата-рейт и адрес пайпа на обеих сторонах
- [ ] Конденсатор на питании обоих модулей nRF
- [ ] Датчик не ответил → бит в `valid` не ставить
- [ ] Антенны вертикально, параллельно друг другу; для 2 км — прямая видимость

---

# Приёмная сторона (Raspberry Pi) — зона шлюза

Сокоманднику с ESP32 эта часть не нужна — только для справки.

## 5. Pi — приём и декодирование (Python)

```python
import struct

FMT = "<BBBhHHHHHBBB"   # 18 байт, little-endian

FIELDS = [  # (bit, поле API, декодер)
    (0, "temp_c",      lambda v: v / 100),
    (1, "humidity",    lambda v: v / 100),
    (2, "pressure",    lambda v: v / 10),
    (3, "alcohol_ppm", float),
    (4, "methane_ppm", float),   # co2 маплю на methane_ppm
    (5, "weight_kg",   lambda v: v / 10),
    (6, "noise_db",    float),
    (7, "battery",     float),
]

def decode(payload: bytes):
    """32-байтный payload nRF -> (seq, dict readings) для POST /api/readings."""
    if len(payload) < 18 or payload[0] != 1:
        return None, None
    (_, seq, valid, t, h, pr, alc, co2,
     w, nz, bat, vib) = struct.unpack(FMT, payload[:18])
    raw = [t, h, pr, alc, co2, w, nz, bat]
    readings = {name: fn(raw[i])
                for i, (bit, name, fn) in enumerate(FIELDS)
                if valid & (1 << bit)}
    return seq, readings
```

Потери пакетов: разрыв `seq` между соседними пакетами больше 1 — были потери.
Полезно логировать при полевом тесте дальности.

## 6. Pi → облако

```
POST https://<render-url>/api/readings
X-API-Key: <INGEST_API_KEY>
Content-Type: application/json

{
  "hive_id": "hive-1",          // имя придумываем сами, улей создастся при первом POST
  "device_id": "esp32-1",
  "sensor_type": "environment",
  "protocol": "nrf24",
  "readings": { ...результат decode()... }
}
```

Разрешённые поля `readings`: `temp_c, humidity, pressure, alcohol_ppm, methane_ppm,
noise_db, weight_kg, battery, vibration`. Любое другое поле → 400.
