
import json
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow requests from any website or dashboard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Find the sample data file in the repository root.
DATA_FILE = (
    Path(__file__).resolve().parent.parent
    / "q-vercel-latency.json"
)


class AnalyticsRequest(BaseModel):
    regions: list[str]
    threshold_ms: float


def get_value(record, possible_names):
    for name in possible_names:
        if name in record:
            return record[name]
    raise ValueError(
        f"Missing one of these fields: {possible_names}"
    )


def percentile_95(values):
    values = sorted(values)

    if not values:
        return None

    # Linear interpolation, like the default NumPy percentile.
    position = 0.95 * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)

    return (
        values[lower]
        + (values[upper] - values[lower])
        * (position - lower)
    )


@app.post("/")
def analytics(request: AnalyticsRequest):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        # Accept either a list or a dictionary containing records.
        if isinstance(data, dict):
            for key in ("records", "data", "telemetry", "pings"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break

        if not isinstance(data, list):
            raise ValueError("Expected a list of telemetry records")

        results = {}

        for region in request.regions:
            records = [
                record for record in data
                if str(get_value(
                    record, ["region", "region_name"]
                )).lower() == region.lower()
            ]

            if not records:
                raise HTTPException(
                    status_code=400,
                    detail=f"No records found for region: {region}",
                )

            latencies = [
                float(get_value(
                    record,
                    ["latency_ms", "latency", "response_time_ms"]
                ))
                for record in records
            ]

            uptimes = [
                float(get_value(
                    record, ["uptime", "uptime_pct", "uptime_percent"]
                ))
                for record in records
            ]

            results[region] = {
                "avg_latency": sum(latencies) / len(latencies),
                "p95_latency": percentile_95(latencies),
                "avg_uptime": sum(uptimes) / len(uptimes),
                "breaches": sum(
                    latency > request.threshold_ms
                    for latency in latencies
                ),
            }

        return results

    except HTTPException:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to process telemetry data: {error}",
        )
