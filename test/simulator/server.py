"""
Standalone sensor simulator server.

Runs on port 5001 (separate from the main app on 5000).
Manages named simulation jobs that generate readings for any schema
defined in the main app and POST them to /api/ingest.

Usage:
    pip install flask requests
    python simulator/server.py

Then open http://localhost:5001 in a browser.
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for

from src.engine import generate_reading

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAIN_API_BASE = os.getenv("MAIN_API_BASE", "http://localhost:5000")
API_KEY = os.getenv("SENSOR_INGEST_TOKEN", "dev-sensor-token")

app = Flask(__name__)
app.secret_key = "sim-secret-key"

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
# jobs: { job_id: { config, thread, stop_event, stats } }
_jobs: dict = {}
_jobs_lock = threading.Lock()
_next_id = 1


def _new_id():
    global _next_id
    _next_id += 1
    return _next_id - 1


# ---------------------------------------------------------------------------
# Simulation worker
# ---------------------------------------------------------------------------

def _worker(job_id, config, stop_event, stats):
    schema_fields = config["schema_fields"]
    interval = float(config.get("interval", 10))
    count_limit = int(config.get("count", 0))
    prev = None
    sent = 0

    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        reading = generate_reading(schema_fields, prev_reading=prev)
        payload = {
            "device_id": config["device_id"],
            "greenhouse_id": config.get("greenhouse_id") or None,
            "schema": config["schema_name"],
            "recorded_at": now.isoformat(),
            "source": "simulator",
            "data": reading,
        }
        try:
            resp = requests.post(
                f"{MAIN_API_BASE}/api/ingest",
                json=payload,
                headers={"X-API-Key": API_KEY},
                timeout=8,
            )
            if resp.status_code >= 400:
                stats["last_error"] = f"HTTP {resp.status_code}: {resp.text[:120]}"
            else:
                stats["sent"] += 1
                stats["last_sent"] = now.isoformat()
                stats["last_reading"] = reading
                stats["last_error"] = None
        except Exception as exc:
            stats["last_error"] = str(exc)[:120]

        prev = reading
        sent += 1
        if count_limit and sent >= count_limit:
            stats["status"] = "done"
            break

        stop_event.wait(timeout=interval)

    if stats.get("status") != "done":
        stats["status"] = "stopped"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------



@app.route("/")
def index():
    return render_template("index.html", main_api=MAIN_API_BASE)


@app.route("/jobs", methods=["POST"])
def create_job():
    schema_name = request.form.get("schema_name", "").strip()
    device_id = request.form.get("device_id", "sim-device-01").strip()
    greenhouse_id = request.form.get("greenhouse_id") or None
    interval = float(request.form.get("interval", 10))
    count = int(request.form.get("count", 0))

    if not schema_name:
        return redirect(url_for("index"))

    # Fetch schema fields from main API
    schema_fields = []
    try:
        resp = requests.get(
            f"{MAIN_API_BASE}/api/schemas",
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        if resp.ok:
            for s in resp.json().get("schemas", []):
                if s["name"] == schema_name:
                    schema_fields = s.get("fields", [])
                    break
    except Exception:
        pass

    if not schema_fields:
        # Fallback: allow simulation with a warning (no fields = empty payloads)
        schema_fields = []

    config = {
        "schema_name": schema_name,
        "schema_fields": schema_fields,
        "device_id": device_id,
        "greenhouse_id": int(greenhouse_id) if greenhouse_id else None,
        "interval": interval,
        "count": count,
    }
    stats = {"status": "running", "sent": 0, "last_sent": None, "last_error": None, "last_reading": None}
    stop_event = threading.Event()

    with _jobs_lock:
        jid = _new_id()
        t = threading.Thread(target=_worker, args=(jid, config, stop_event, stats), daemon=True)
        _jobs[jid] = {"config": config, "thread": t, "stop_event": stop_event, "stats": stats}
        t.start()

    return redirect(url_for("index"))


@app.route("/jobs/<int:job_id>/stop", methods=["POST"])
def stop_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job:
        job["stop_event"].set()
    return redirect(url_for("index"))


@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
def delete_job(job_id):
    with _jobs_lock:
        job = _jobs.pop(job_id, None)
    if job:
        job["stop_event"].set()
    return redirect(url_for("index"))


@app.route("/proxy/schemas")
def proxy_schemas():
    """Proxy GET /api/schemas from the main API so the browser avoids cross-origin issues."""
    try:
        resp = requests.get(
            f"{MAIN_API_BASE}/api/schemas",
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        return (resp.content, resp.status_code, {"Content-Type": "application/json"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/proxy/greenhouses")
def proxy_greenhouses():
    """Proxy GET /api/greenhouses from the main API so the browser avoids cross-origin issues."""
    try:
        resp = requests.get(
            f"{MAIN_API_BASE}/api/greenhouses",
            headers={"X-API-Key": API_KEY},
            timeout=5,
        )
        return (resp.content, resp.status_code, {"Content-Type": "application/json"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/jobs")
def api_jobs():
    with _jobs_lock:
        jobs = []
        for jid, job in _jobs.items():
            jobs.append({
                "id": jid,
                "schema_name": job["config"]["schema_name"],
                "device_id": job["config"]["device_id"],
                "greenhouse_id": job["config"].get("greenhouse_id"),
                "interval": job["config"].get("interval", 10),
                "status": job["stats"]["status"],
                "sent": job["stats"]["sent"],
                "last_sent": job["stats"].get("last_sent"),
                "last_error": job["stats"].get("last_error"),
                "last_reading": job["stats"].get("last_reading"),
            })
    return jsonify(jobs)


@app.route("/api/status")
def api_status():
    with _jobs_lock:
        result = {}
        for jid, job in _jobs.items():
            result[jid] = {
                "schema": job["config"]["schema_name"],
                "device_id": job["config"]["device_id"],
                "status": job["stats"]["status"],
                "sent": job["stats"]["sent"],
                "last_sent": job["stats"].get("last_sent"),
            }
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.getenv("SIM_PORT", 5001))
    print(f"Simulator server starting on http://localhost:{port}")
    print(f"Pushing data to: {MAIN_API_BASE}")
    app.run(host="0.0.0.0", port=port, debug=False)
