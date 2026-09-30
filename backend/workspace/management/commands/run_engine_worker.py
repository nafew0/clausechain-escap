import fcntl
import os
import signal
import socket
import threading

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection
from django.utils import timezone

from workspace.engine_worker import claim_next_action, execute_action
from workspace.models import EngineWorkerHeartbeat
from workspace.worker_supervisor import HEARTBEAT_SECONDS


class Command(BaseCommand):
    help = "Claim and execute allowlisted ClauseChain engine actions."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=2.0)

    def _acquire_single_instance_lock(self):
        """One worker per host. Best effort: where the lock dir is not writable
        (e.g. production, where systemd already guarantees a single worker)
        the worker runs without it."""
        try:
            settings.WORKSPACE_LOCK_DIR.mkdir(parents=True, exist_ok=True)
            handle = open(settings.WORKSPACE_LOCK_DIR / "engine_worker.lock", "a")
        except OSError:
            return True, None
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False, None
        return True, handle

    def _heartbeat_loop(self, worker_id, state, stop):
        started = timezone.now()
        while not stop.is_set():
            try:
                EngineWorkerHeartbeat.objects.update_or_create(
                    worker_id=worker_id,
                    defaults={
                        "hostname": socket.gethostname()[:255],
                        "pid": os.getpid(),
                        "started_at": started,
                        "last_seen": timezone.now(),
                        "current_action_id": state.get("action_id"),
                    },
                )
            except Exception as exc:  # liveness must never kill the worker
                self.stderr.write(f"heartbeat failed: {exc}")
            finally:
                close_old_connections()
            stop.wait(HEARTBEAT_SECONDS)
        connection.close()

    def handle(self, *args, **options):
        ok, lock = self._acquire_single_instance_lock()
        if not ok:
            self.stdout.write("Another engine worker is already running on this host; exiting.")
            return
        worker_id = f"{socket.gethostname()}:{os.getpid()}"[:255]
        state, stop = {}, threading.Event()
        beat = threading.Thread(
            target=self._heartbeat_loop, args=(worker_id, state, stop), daemon=True
        )
        beat.start()
        # SIGTERM/SIGHUP drain the worker: the running action finishes, nothing
        # new is claimed, then it exits. A restart for new code never kills a run.
        draining = threading.Event()

        def drain(signum, frame):
            draining.set()
            self.stdout.write("Stop requested: finishing the current action, then exiting.")

        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, drain)
        self.stdout.write(f"Engine worker {worker_id} started")
        try:
            while not draining.is_set():
                action = claim_next_action()
                if action is not None:
                    state["action_id"] = action.pk
                    self.stdout.write(f"Running {action.kind} action {action.pk}")
                    execute_action(action)
                    self.stdout.write(f"Action {action.pk}: {action.status}")
                    state["action_id"] = None
                if options["once"]:
                    return
                draining.wait(max(0.25, options["poll_seconds"]))
        finally:
            stop.set()
            beat.join(timeout=HEARTBEAT_SECONDS + 1)
            EngineWorkerHeartbeat.objects.filter(worker_id=worker_id).delete()
            if lock is not None:
                lock.close()
