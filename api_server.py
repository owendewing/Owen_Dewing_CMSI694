"""
HTTP API to run the Last.fm ingest → Spotify genres → feature engineering pipeline.
Start: uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from dashboard_data import build_dashboard_payload

app = FastAPI(title="Listening analytics pipeline")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FetchBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)


def run_step(script_args: list[str]) -> tuple[str, str]:
    """
    Run a pipeline script. Stdout is discarded to avoid OS pipe deadlocks when child
    processes emit a lot of output (pandas, APIs, etc.); stderr is written to a
    temp file and read back after the process exits.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    stderr_path = ROOT / ".pipeline_step_stderr.log"
    with open(stderr_path, "wb") as err_f:
        proc = subprocess.run(
            [sys.executable, *script_args],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=err_f,
        )
    err_text = ""
    try:
        err_text = stderr_path.read_text(errors="replace")[-12000:]
    except OSError:
        err_text = ""
    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "step": script_args[0],
                "stderr": err_text,
                "stdout": "",
            },
        )
    return "", err_text


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard/{username}")
def get_dashboard(username: str):
    return build_dashboard_payload(ROOT, username.strip())


@app.post("/api/fetch-data")
def fetch_data(body: FetchBody):
    """
    Runs: lastfm.py → spotify_client.py → feature_engineering.py
    """
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")

    steps: list[list[str]] = [
        ["lastfm.py", "--username", username],
        ["spotify_client.py"],
        [
            "feature_engineering.py",
            "--scrobbles-folder",
            f"{username}_scrobbles",
            "--output-prefix",
            username,
        ],
    ]

    for script_args in steps:
        run_step(script_args)

    return {
        "ok": True,
        "username": username,
        "message": "Pipeline ran successfully.",
    }
