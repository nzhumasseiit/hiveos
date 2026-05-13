from fastapi import APIRouter, Depends, Query
from influxdb_client import InfluxDBClient
import os, sys
import re
from datetime import datetime, timedelta
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from main import verify_token

router = APIRouter()
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

def get_influx():
    return InfluxDBClient(
        url=os.getenv("INFLUX_URL"),
        token=os.getenv("INFLUX_TOKEN"),
        org=os.getenv("INFLUX_ORG")
    )

@router.get("/data")
def get_data(
    node: str = Query("lid", description="Node name e.g. lid, f1, f2"),
    hours: int = Query(24, ge=1, le=168, description="How many hours back (1-168)"),
    username: str = Depends(verify_token)
):
    """Returns hourly-averaged sensor readings for a node over the last N hours."""
    if not _NODE_RE.match(node):
        return {"node": node, "hours": hours, "data": {}}
    client = get_influx()
    query_api = client.query_api()
    bucket = os.getenv("INFLUX_BUCKET", "beehive")

    fields = ["temp_c", "humidity", "pressure", "alcohol_ppm", "methane_ppm", "noise_db", "weight_kg"]
    result = {}

    for field in fields:
        query = f"""
from(bucket: "{bucket}")
  |> range(start: -{hours}h)
  |> filter(fn: (r) => r._measurement == "hive_sensors")
  |> filter(fn: (r) => r.node == "{node}")
  |> filter(fn: (r) => r._field == "{field}")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> yield(name: "mean")
"""
        try:
            tables = query_api.query(query)
            values = []
            for table in tables:
                for record in table.records:
                    values.append({
                        "time": record.get_time().isoformat(),
                        "value": round(record.get_value(), 2)
                    })
            result[field] = values
        except Exception as e:
            result[field] = []

    client.close()
    return {"node": node, "hours": hours, "data": result}


@router.get("/data/latest")
def get_latest(
    node: str = Query("lid"),
    username: str = Depends(verify_token)
):
    """Returns the single most recent reading for each field — used by the AI context."""
    if not _NODE_RE.match(node):
        return {}
    client = get_influx()
    query_api = client.query_api()
    bucket = os.getenv("INFLUX_BUCKET", "beehive")

    query = f"""
from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "hive_sensors")
  |> filter(fn: (r) => r.node == "{node}")
  |> last()
"""
    snapshot = {}
    try:
        tables = query_api.query(query)
        for table in tables:
            for record in table.records:
                snapshot[record.get_field()] = round(record.get_value(), 2)
    except:
        pass

    client.close()
    return snapshot
