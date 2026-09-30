"""Engine worker liveness + development auto-start.

The worker records a heartbeat row every few seconds. Queueing an action calls
ensure_worker(): if no heartbeat is fresh and ENGINE_WORKER_AUTOSTART is on, a
detached `manage.py run_engine_worker` is started. The worker itself holds an
exclusive lock, so a racing second start exits immediately.
"""
import os
import subprocess
import sys
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EngineWorkerHeartbeat

HEARTBEAT_SECONDS = 5
STALE_AFTER_SECONDS = 20
SPAWN_GRACE_SECONDS = 30


def worker_status():
    latest = EngineWorkerHeartbeat.objects.order_by("-last_seen").first()
    now = timezone.now()
    alive = bool(latest and latest.last_seen >= now - timedelta(seconds=STALE_AFTER_SECONDS))
    return {
        "alive": alive,
        "autostart": bool(settings.ENGINE_WORKER_AUTOSTART),
        "last_seen": latest.last_seen.isoformat() if latest else None,
        "hostname": latest.hostname if latest else None,
        "pid": latest.pid if latest else None,
        "current_action_id": (
            str(latest.current_action_id) if latest and alive and latest.current_action_id else None
        ),
    }


def _spawn_stamp():
    return settings.WORKSPACE_LOCK_DIR / "engine_worker.spawned"


def ensure_worker():
    """Start a background worker if none is alive. Returns status + `started`."""
    status = worker_status()
    if status["alive"] or not status["autostart"]:
        return status | {"started": False}
    stamp = _spawn_stamp()
    try:
        # A worker was started moments ago and is still booting: don't pile on.
        if time.time() - stamp.stat().st_mtime < SPAWN_GRACE_SECONDS:
            return status | {"started": False, "starting": True}
    except OSError:
        pass
    log_path = settings.ENGINE_WORKER_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, str(settings.BASE_DIR / "manage.py"), "run_engine_worker"],
            cwd=settings.BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # survives the request / dev-server reloads
            close_fds=True,
            env=os.environ.copy(),
        )
    stamp.write_text(str(process.pid), encoding="utf-8")
    return status | {"started": True, "starting": True, "pid": process.pid}
