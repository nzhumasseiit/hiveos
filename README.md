# HiveOS

HiveOS is an IoT monitoring platform for smart beehives. It collects sensor data from edge devices, stores hive health metrics in InfluxDB, and visualizes real-time and historical trends through Grafana dashboards. The backend manages authentication, hive/device metadata, sensor ingestion, and API access, with a simple path toward multi-hive deployments and client-facing monitoring.

## Architecture

```text
Raspberry Pi / ESP32 sensors
  -> POST /api/readings
  -> FastAPI backend
  -> InfluxDB time-series bucket
  -> Grafana dashboards

Browser frontend
  -> JWT login
  -> hive/device metadata, latest readings, history, AI assistant
```

## Features

- JWT-protected backend API
- Environment-based admin credentials and JWT secret
- Multi-hive metadata model with owner, client, location, status, and last-seen fields
- Device registry with device ID, sensor type, protocol, and last-seen status
- InfluxDB storage using tags for `hive_id`, `device_id`, `sensor_type`, and `node`
- Protected edge-device ingestion endpoint
- Grafana datasource provisioning for local demos
- Optional OpenAI-backed HiveAI assistant, with the API key kept server-side

## Tech Stack

- Python, FastAPI, Pydantic
- SQLite for lightweight hive/device metadata
- InfluxDB for sensor time-series data
- Grafana for dashboarding
- Docker Compose for local API, InfluxDB, and Grafana
- Raspberry Pi / ESP32 edge devices using I2C, 1-Wire, I2S, GPIO, and ADC sensors

## Quickstart

```bash
cd hiveos
cp backend/.env.example backend/.env
```

If `backend/.env` already exists, compare it with `backend/.env.example` and add any missing variables. Edit `backend/.env` and set at least:

```text
JWT_SECRET=<long-random-secret>
ADMIN_PASSWORD=<demo-admin-password>
INGEST_API_KEY=<random-edge-device-key>
```

Start the local stack:

```bash
docker compose up --build
```

Then open:

- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Grafana: http://localhost:3000
- InfluxDB: http://localhost:8086
- Frontend: open `frontend/index.html` in a browser

For a non-Docker backend run:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `ENV` | `development` or `production` |
| `JWT_SECRET` | Secret used to sign JWTs. Required in production |
| `JWT_EXP_HOURS` | Login token lifetime |
| `ADMIN_USERNAME` | Initial demo/admin login username |
| `ADMIN_PASSWORD` | Initial demo/admin login password |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `DB_PATH` | SQLite metadata database path |
| `INFLUX_URL` | InfluxDB URL |
| `INFLUX_TOKEN` | InfluxDB API token |
| `INFLUX_ORG` | InfluxDB organization |
| `INFLUX_BUCKET` | InfluxDB bucket for hive sensor metrics |
| `INGEST_API_KEY` | API key edge devices use with `X-API-Key` |
| `OPENAI_API_KEY` | Optional server-side key for `/api/chat` |
| `OPENAI_MODEL` | Model used by the HiveAI assistant |

## API Examples

Login:

```bash
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_ADMIN_PASSWORD"}'
```

Create a hive:

```bash
curl -X POST http://localhost:8000/api/hives \
  -H "Authorization: Bearer YOUR_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hive Alpha",
    "location": "North field, row 2",
    "client_id": "demo-client",
    "topic": "hive/alpha",
    "node": "node-01"
  }'
```

Ingest a reading from an edge device:

```bash
curl -X POST http://localhost:8000/api/readings \
  -H "X-API-Key: YOUR_INGEST_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "hive_id": "HIVE_ID_FROM_API",
    "device_id": "node-01",
    "sensor_type": "environment",
    "protocol": "i2c",
    "readings": {
      "temp_c": 35.2,
      "humidity": 58.4,
      "weight_kg": 42.8,
      "battery": 87
    }
  }'
```

Query history:

```bash
curl "http://localhost:8000/api/data?hive_id=HIVE_ID&device_id=node-01&hours=24" \
  -H "Authorization: Bearer YOUR_JWT"
```

## Grafana And InfluxDB

Docker Compose provisions a Grafana datasource named `HiveOS InfluxDB`. Create dashboard panels with Flux queries like:

```flux
from(bucket: "beehive")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "hive_sensors")
  |> filter(fn: (r) => r.hive_id == "HIVE_ID")
  |> filter(fn: (r) => r._field == "temp_c")
  |> aggregateWindow(every: 15m, fn: mean, createEmpty: false)
```

Recommended demo panels:

- Temperature
- Humidity
- Hive weight
- Battery level
- Noise/vibration
- Device last seen/status

## Security Notes

- Never commit `.env`, real tokens, JWT secrets, passwords, OpenAI keys, InfluxDB tokens, or SQLite database files.
- `backend/.env.example` contains placeholders and local demo defaults only.
- Set `ENV=production` for deployments; the API will refuse to start without required secrets.
- Use a long random `JWT_SECRET` and a separate random `INGEST_API_KEY`.
- Keep `OPENAI_API_KEY` only on the backend. The frontend calls `/api/chat`; it must never receive the key.
- Replace all Docker demo passwords before any shared or internet-exposed deployment.

## Current Status

This repository is suitable as a private portfolio/client demo baseline. It includes a working backend, frontend, local Compose stack, secure configuration pattern, hive/device registry, InfluxDB integration, and optional AI assistant.

## Roadmap

- Add persistent user and role tables: `admin`, `beekeeper`, `viewer`
- Add client/team ownership and invitation flows
- Add alert rules and anomaly events stored in a dedicated table or Influx measurement
- Add Grafana dashboard JSON provisioning
- Add edge-device sample scripts for Raspberry Pi and ESP32
- Add automated tests for auth, hive/device metadata, and ingestion
