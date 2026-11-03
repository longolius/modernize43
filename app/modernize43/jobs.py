"""In-memory job registry with one worker and one temporary directory per job."""

import os
import queue
import shutil
import tempfile
import threading
import time
import uuid

from .source import INTRO_URL, SourceError, probe
from .transcode import transcode

JOB_TIMEOUT_SECONDS = 180
RETENTION_MINUTES = 60


class Job:
    def __init__(self, url, logo="none", seconds=30, intro="none"):
        self.id = uuid.uuid4().hex[:10]
        self.url = url
        self.logo = logo
        self.seconds = seconds
        self.intro = intro
        self.state = "queued"
        self.message = ""
        self.directory = None
        self.result_path = None
        self.created = time.time()

    def public(self):
        payload = {"id": self.id, "state": self.state}
        if self.message:
            payload["message"] = self.message
        if self.state == "done":
            payload["result_url"] = "/jobs/%s/result.mp4" % self.id
        return payload


class JobManager:
    def __init__(self, allow_private, retention_minutes=RETENTION_MINUTES,
                 timeout=JOB_TIMEOUT_SECONDS):
        self.allow_private = allow_private
        self.retention = retention_minutes * 60
        self.timeout = timeout
        self.jobs = {}
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        threading.Thread(target=self._work, daemon=True).start()
        threading.Thread(target=self._clean, daemon=True).start()

    def create(self, url, logo="none", seconds=30, intro="none"):
        job = Job(url, logo, seconds, intro)
        with self.lock:
            self.jobs[job.id] = job
        self.queue.put(job)
        return job

    def get(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

    def _work(self):
        while True:
            job = self.queue.get()
            started = time.time()
            with self.lock:
                job.state = "running"
            directory = tempfile.mkdtemp(prefix="modernize43-%s-" % job.id)
            job.directory = directory
            output = os.path.join(directory, "result.mp4")
            try:
                remaining = self.timeout - (time.time() - started)
                info = probe(job.url, timeout=max(1, min(60, int(remaining))))
                limit = (16.0 / 9.0) / 1.01
                if info["dar"] >= limit:
                    raise SourceError(
                        "Das Seitenverhältnis (aspect ratio %.2f) ist nicht schmaler "
                        "als 16:9." % info["dar"])
                remaining = self.timeout - (time.time() - started)
                if remaining <= 0:
                    raise SourceError("Das Zeitlimit von %d Sekunden ist überschritten."
                                      % self.timeout)
                transcode(job.url, output, info, timeout=int(remaining), logo=job.logo,
                          seconds=job.seconds,
                          intro_url=INTRO_URL if job.intro == "joyn" else None)
                if not os.path.isfile(output) or os.path.getsize(output) == 0:
                    raise SourceError("Es wurde keine Ausgabedatei erzeugt.")
                with self.lock:
                    job.result_path = output
                    job.state = "done"
            except Exception as exc:  # noqa: BLE001 - every failure becomes a job message
                message = str(exc) or exc.__class__.__name__
                with self.lock:
                    job.state = "error"
                    job.message = message[:2000]
            finally:
                self.queue.task_done()

    def _clean(self):
        while True:
            time.sleep(60)
            cutoff = time.time() - self.retention
            with self.lock:
                expired = [job for job in self.jobs.values() if job.created < cutoff]
                for job in expired:
                    self.jobs.pop(job.id, None)
            for job in expired:
                if job.directory:
                    shutil.rmtree(job.directory, ignore_errors=True)
