from datetime import datetime
import re
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from pydantic import BaseModel, Field

from config import get_settings
from security import verify_ingest_key, verify_token
from storage import ensure_hive, init_db, touch_device


router = APIRouter()
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_FIELDS = [
    "temp_c",
    "humidity",
    "pressure",
    "alcohol_ppm",
    "methane_ppm",
    "noise_db",
    "weight_kg",
    "battery",
    "vibration",
]


class SensorReading(BaseModel):
    hive_id: str = Field(min_length=1, max_length=64)
    device_id: str = Field(min_length=1, max_length=64)
    sensor_type: str = Field(default="environment", min_length=1, max_length=64)
    protocol: str = Field(default="unknown", max_length=32)
    timestamp: Optional[datetime] = None
    readings: Dict[str, float] = Field(default_factory=dict)
    status: Optional[str] = Field(default=None, max_length=64)


def _validate_id(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not _ID_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field_name} format")
    return value


def _get_influx() -> InfluxDBClient:
    settings = get_settings()
    if not settings.influx_url or not settings.influx_token or not settings.influx_org:
        raise HTTPException(status_code=503, detail="InfluxDB is not configured")
    return InfluxDBClient(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )


def _tag_filter(tag: str, value: Optional[str]) -> str:
    if not value:
        return ""
    return f'  |> filter(fn: (r) => r.{tag} == "{value}")\n'


@router.post("/readings", dependencies=[Depends(verify_ingest_key)])
def ingest_reading(body: SensorReading):
    """Ingest one edge-device reading batch into InfluxDB."""
    _validate_id(body.hive_id, "hive_id")
    _validate_id(body.device_id, "device_id")
    _validate_id(body.sensor_type, "sensor_type")

    if not body.readings and body.status is None:
        raise HTTPException(status_code=400, detail="At least one reading or status is required")

    init_db()
    # Auto-register unknown hives so edge devices don't need the JWT-protected /hives flow.
    ensure_hive(body.hive_id, body.device_id)

    point = (
        Point("hive_sensors")
        .tag("hive_id", body.hive_id)
        .tag("device_id", body.device_id)
        .tag("sensor_type", body.sensor_type)
        .tag("node", body.device_id)
    )
    for key, value in body.readings.items():
        if key not in _FIELDS:
            raise HTTPException(status_code=400, detail=f"Unsupported reading field: {key}")
        point.field(key, float(value))
    if body.status is not None:
        point.field("status", body.status)
    if body.timestamp is not None:
        point.time(body.timestamp, WritePrecision.NS)

    settings = get_settings()
    client = None
    try:
        client = _get_influx()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=point)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="InfluxDB write failed") from exc
    finally:
        try:
            client.close()
        except Exception:
            pass

    touch_device(body.hive_id, body.device_id, body.sensor_type, body.protocol)
    return {"accepted": True}


@router.get("/data")
def get_data(
    node: str = Query("lid", description="Backward-compatible device/node id"),
    hive_id: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    sensor_type: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168, description="How many hours back (1-168)"),
    username: str = Depends(verify_token),
):
    """Returns hourly averaged sensor readings for a node/device over the last N hours."""
    device = _validate_id(device_id or node, "device_id")
    _validate_id(hive_id, "hive_id")
    _validate_id(sensor_type, "sensor_type")

    settings = get_settings()
    result = {}
    client = None

    try:
        client = _get_influx()
        query_api = client.query_api()

        for field in _FIELDS:
            query = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "hive_sensors")
{_tag_filter("hive_id", hive_id)}{_tag_filter("device_id", device)}{_tag_filter("sensor_type", sensor_type)}  |> filter(fn: (r) => r._field == "{field}")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> yield(name: "mean")
"""
            tables = query_api.query(query)
            values = []
            for table in tables:
                for record in table.records:
                    values.append(
                        {
                            "time": record.get_time().isoformat(),
                            "value": round(record.get_value(), 2),
                        }
                    )
            result[field] = values
    except HTTPException as exc:
        return {"node": device, "hours": hours, "data": {}, "warning": exc.detail}
    except Exception:
        return {"node": device, "hours": hours, "data": {}, "warning": "InfluxDB query failed"}
    finally:
        try:
            client.close()
        except Exception:
            pass

    return {"node": device, "hive_id": hive_id, "sensor_type": sensor_type, "hours": hours, "data": result}


@router.get("/data/latest")
def get_latest(
    node: str = Query("lid"),
    hive_id: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    sensor_type: Optional[str] = Query(None),
    username: str = Depends(verify_token),
):
    """Returns the most recent reading for each field, used by the AI context."""
    device = _validate_id(device_id or node, "device_id")
    _validate_id(hive_id, "hive_id")
    _validate_id(sensor_type, "sensor_type")

    settings = get_settings()
    query = f"""
from(bucket: "{settings.influx_bucket}")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "hive_sensors")
{_tag_filter("hive_id", hive_id)}{_tag_filter("device_id", device)}{_tag_filter("sensor_type", sensor_type)}  |> last()
"""
    snapshot = {}
    client = None
    try:
        client = _get_influx()
        tables = client.query_api().query(query)
        for table in tables:
            for record in table.records:
                value = record.get_value()
                snapshot[record.get_field()] = round(value, 2) if isinstance(value, (int, float)) else value
    except HTTPException:
        return {}
    except Exception:
        return {}
    finally:
        try:
            client.close()
        except Exception:
            pass
    return snapshot


@router.get("/alerts")
def get_alerts(
    hive_id: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    username: str = Depends(verify_token),
):
    """Placeholder alert feed for the demo; anomaly persistence belongs in the next milestone."""
    _validate_id(hive_id, "hive_id")
    _validate_id(device_id, "device_id")
    return {
        "alerts": [],
        "status": "no_active_alerts",
        "scope": {"hive_id": hive_id, "device_id": device_id},
    }
