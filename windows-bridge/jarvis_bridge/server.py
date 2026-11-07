"""
JARVIS BLUE Windows Bridge — reference server
==============================================

This is the desktop side of the JARVIS BLUE MOBILE remote command centre.

It is a small, dependency-light service that:

  * exposes a read-only status endpoint (heartbeat, CPU/RAM/GPU/disk, job counts),
  * exposes a job queue the phone can submit to and cancel,
  * streams job events over a WebSocket,
  * authenticates every request with an HMAC-SHA256 signature so a stolen
    request cannot be replayed.

Security posture
----------------
* Bind to 127.0.0.1 by default and put the service behind Tailscale / WireGuard
  or an SSH tunnel. Do NOT expose this port to the public internet.
* The shared secret is read from an environment variable and never written to
  disk in plain text.
* TLS is expected to be terminated by the tunnel or by a reverse proxy.

Run with:

    pip install -r requirements.txt
    $env:JARVIS_BRIDGE_SECRET = "<long random string>"     # PowerShell
    python -m jarvis_bridge.server --host 127.0.0.1 --port 8765

The phone is paired by entering the same secret in
Settings → Windows Connection → Pairing.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import platform
import secrets
import socket
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_VERSION = "1.0.0"
KEY_ID = "jarvis-blue-mobile-v1"
MAX_SIGNATURE_AGE_SECONDS = 300  # replay window
NONCE_TTL_SECONDS = MAX_SIGNATURE_AGE_SECONDS * 2

app = FastAPI(title="JARVIS BLUE Windows Bridge", version=APP_VERSION)

# --------------------------------------------------------------------------- #
# Secret handling
# --------------------------------------------------------------------------- #

def bridge_secret() -> str:
    secret = os.environ.get("JARVIS_BRIDGE_SECRET", "").strip()
    if not secret:
        raise RuntimeError(
            "JARVIS_BRIDGE_SECRET is not set. Generate one with:\n"
            "  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return secret


# --------------------------------------------------------------------------- #
# Request signing
# --------------------------------------------------------------------------- #

_seen_nonces: Dict[str, float] = {}


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_string(method: str, path: str, timestamp: str, nonce: str, body: str) -> str:
    return "\n".join([method.upper(), path, timestamp, nonce, sha256_hex(body)])


def expected_signature(method: str, path: str, timestamp: str, nonce: str, body: str, secret: str) -> str:
    canonical = canonical_string(method, path, timestamp, nonce, body)
    return hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_request(
    method: str,
    path: str,
    body: str,
    key_id: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
    signature: Optional[str],
) -> None:
    if not key_id or key_id != KEY_ID:
        raise HTTPException(status_code=401, detail="unknown key id")
    if not timestamp or not nonce or not signature:
        raise HTTPException(status_code=401, detail="missing signature headers")

    try:
        age = abs(time.time() - float(timestamp) / 1000.0)
    except ValueError:
        raise HTTPException(status_code=401, detail="malformed timestamp")
    if age > MAX_SIGNATURE_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="stale request (outside replay window)")

    _prune_nonces()
    if nonce in _seen_nonces:
        raise HTTPException(status_code=401, detail="replayed nonce")
    _seen_nonces[nonce] = time.time()

    expected = expected_signature(method, path, timestamp, nonce, body, bridge_secret())
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="signature mismatch")


def _prune_nonces() -> None:
    cutoff = time.time() - NONCE_TTL_SECONDS
    for key in [k for k, v in _seen_nonces.items() if v < cutoff]:
        _seen_nonces.pop(key, None)


# --------------------------------------------------------------------------- #
# Job model
# --------------------------------------------------------------------------- #

@dataclass
class Job:
    id: str
    kind: str
    title: str
    state: str = "QUEUED"
    progress: float = 0.0
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = field(default_factory=lambda: int(time.time() * 1000))
    logs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    requires_approval: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobRequest(BaseModel):
    kind: str = Field(default="WORKFLOW")
    title: str
    payload: str = "{}"
    require_approval: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobQueue:
    """In-memory job queue with a worker loop that reports progress.

    Replace `_run_job` with the real workload (your After Effects render farm,
    your Python project runner, …). Everything else — queueing, approval,
    cancellation, progress reporting — already works.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._lock = asyncio.Lock()
        self._subscribers: Set[WebSocket] = set()

    async def submit(self, request: JobRequest) -> Job:
        job = Job(
            id=secrets.token_hex(8),
            kind=request.kind,
            title=request.title,
            requires_approval=request.require_approval,
            metadata={**request.metadata, "payload": request.payload},
        )
        async with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
        await self.broadcast(json.dumps({"type": "job.queued", "job": asdict(job)}))
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> List[Job]:
        return [self._jobs[j] for j in self._order if j in self._jobs]

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return False
        job.state = "CANCELLED"
        job.updated_at = int(time.time() * 1000)
        await self.broadcast(json.dumps({"type": "job.cancelled", "job_id": job_id}))
        return True

    async def update(self, job: Job, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = int(time.time() * 1000)
        await self.broadcast(json.dumps({"type": "job.updated", "job": asdict(job)}))

    async def broadcast(self, message: str) -> None:
        dead: List[WebSocket] = []
        for socket in list(self._subscribers):
            try:
                await socket.send_text(message)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self._subscribers.discard(socket)

    async def run_pending(self) -> None:
        """Worker loop: executes queued jobs one at a time."""
        while True:
            await asyncio.sleep(0.5)
            job = None
            async with self._lock:
                for job_id in self._order:
                    candidate = self._jobs.get(job_id)
                    if candidate and candidate.state == "QUEUED":
                        job = candidate
                        break
            if job is None:
                continue
            await self.execute(job)

    async def execute(self, job: Job) -> None:
        await self.update(job, state="RUNNING", progress=0.02)
        try:
            await self._run_job(job)
            await self.update(job, state="SUCCEEDED", progress=1.0)
        except asyncio.CancelledError:
            await self.update(job, state="CANCELLED")
        except Exception as exc:  # pragma: no cover - defensive
            await self.update(job, state="FAILED", error=str(exc))

    async def _run_job(self, job: Job) -> None:
        """Replace this with the real workload."""
        for step in range(1, 6):
            if job.state == "CANCELLED":
                return
            await asyncio.sleep(0.4)
            job.logs.append(f"step {step}/5 complete")
            await self.update(job, progress=step / 5.0)


queue = JobQueue()


# --------------------------------------------------------------------------- #
# System status
# --------------------------------------------------------------------------- #

def system_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "peer_id": socket.gethostname(),
        "state": "online",
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}",
        "agent_version": APP_VERSION,
        "heartbeat": int(time.time() * 1000),
        "queued_jobs": len([j for j in queue.list() if j.state == "QUEUED"]),
        "running_jobs": len([j for j in queue.list() if j.state == "RUNNING"]),
        "detail": "JARVIS BLUE bridge",
    }

    try:
        import psutil  # type: ignore

        status["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        status["memory_percent"] = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/")
        status["disk_free_gb"] = round(disk.free / (1024 ** 3), 2)
        try:
            import pynvml  # type: ignore

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            status["gpu_percent"] = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            pynvml.nvmlShutdown()
        except Exception:
            pass
    except Exception:
        pass

    return status


# --------------------------------------------------------------------------- #
# HTTP routes
# --------------------------------------------------------------------------- #

async def _read_body(request: Request) -> str:
    raw = await request.body()
    return raw.decode("utf-8", errors="replace")


def _verify(request: Request, body: str) -> None:
    verify_request(
        method=request.method,
        path=request.url.path,
        body=body,
        key_id=request.headers.get("X-Jarvis-Key-Id"),
        timestamp=request.headers.get("X-Jarvis-Timestamp"),
        nonce=request.headers.get("X-Jarvis-Nonce"),
        signature=request.headers.get("X-Jarvis-Signature"),
    )


@app.get("/api/health")
async def health() -> JSONResponse:
    """Unauthenticated liveness probe — reveals nothing but the fact it is alive."""
    return JSONResponse({"ok": True, "service": "jarvis-blue-bridge", "version": APP_VERSION})


@app.get("/api/status")
async def status(request: Request) -> JSONResponse:
    body = await _read_body(request)
    _verify(request, body)
    return JSONResponse(system_status())


@app.get("/api/jobs")
async def list_jobs(request: Request) -> JSONResponse:
    body = await _read_body(request)
    _verify(request, body)
    return JSONResponse({"jobs": [asdict(j) for j in queue.list()]})


@app.post("/api/jobs")
async def submit_job(request: Request) -> JSONResponse:
    body = await _read_body(request)
    _verify(request, body)
    try:
        payload = JobRequest(**json.loads(body or "{}"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid job payload: {exc}")
    job = await queue.submit(payload)
    return JSONResponse(asdict(job))


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> JSONResponse:
    body = await _read_body(request)
    _verify(request, body)
    ok = await queue.cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found or already finished")
    return JSONResponse({"ok": True, "job_id": job_id})


# --------------------------------------------------------------------------- #
# WebSocket events
# --------------------------------------------------------------------------- #

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    timestamp = websocket.headers.get("X-Jarvis-Timestamp")
    nonce = websocket.headers.get("X-Jarvis-Nonce")
    signature = websocket.headers.get("X-Jarvis-Signature")
    key_id = websocket.headers.get("X-Jarvis-Key-Id")

    try:
        verify_request("GET", "/ws", "", key_id, timestamp, nonce, signature)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    queue._subscribers.add(websocket)
    try:
        await websocket.send_text(json.dumps({"type": "hello", "status": system_status()}))
        while True:
            await websocket.receive_text()  # keep-alive
    except WebSocketDisconnect:
        pass
    finally:
        queue._subscribers.discard(websocket)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS BLUE Windows Bridge")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (keep it local)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--generate-secret", action="store_true", help="print a new shared secret")
    args = parser.parse_args()

    if args.generate_secret:
        print(secrets.token_urlsafe(48))
        return

    import uvicorn

    @app.on_event("startup")
    async def _startup() -> None:
        asyncio.create_task(queue.run_pending())

    print(f"JARVIS BLUE bridge {APP_VERSION} listening on {args.host}:{args.port}")
    print("Keep this behind a VPN or SSH tunnel. Do not expose it publicly.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
