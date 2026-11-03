"""The HTTP interface: form, job page, status JSON, download and health check."""

import html
import json
import os
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler

from .source import ARABELLA_URL, SourceError, validate_url

JOB_PATH = re.compile(r"^/jobs/([A-Za-z0-9]+)$")
STATUS_PATH = re.compile(r"^/jobs/([A-Za-z0-9]+)/status$")
RESULT_PATH = re.compile(r"^/jobs/([A-Za-z0-9]+)/result\.mp4$")
RANGE_HEADER = re.compile(r"^bytes=(\d*)-(\d*)$")

STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: #101215; color: #e8eaed; }
main { max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 1.5rem; margin: 0 0 6px; }
p.lead { color: #9aa0a6; margin: 0 0 24px; }
form { display: flex; gap: 8px; flex-wrap: wrap; }
input[type=url] { flex: 1 1 420px; padding: 12px 14px; border-radius: 8px;
  border: 1px solid #33383e; background: #1a1d21; color: inherit; font-size: 1rem; }
button { padding: 12px 20px; border-radius: 8px; border: 0; background: #4c8dff;
  color: #06101f; font-weight: 600; font-size: 1rem; cursor: pointer; }
video { width: 100%; border-radius: 10px; background: #000; margin: 16px 0; }
a.download { display: inline-block; padding: 12px 20px; border-radius: 8px;
  background: #1f2429; color: #e8eaed; text-decoration: none; border: 1px solid #33383e; }
.status { padding: 14px 16px; border-radius: 8px; background: #1a1d21;
  border: 1px solid #33383e; margin: 18px 0; }
.error { border-color: #7a2b2b; background: #2a1717; color: #ffb4b4; }
.muted { color: #9aa0a6; font-size: .9rem; }
"""


def page(title, body):
    return ("<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>%s</title><style>%s</style></head><body><main>%s</main></body></html>"
            % (html.escape(title), STYLE, body))


def select(name, choices, current):
    options = "".join(
        "<option value=\"%s\"%s>%s</option>" % (value, " selected" if value == current else "", label)
        for value, label in choices)
    return "<select name=\"%s\">%s</select>" % (name, options)


def form(value="", logo="none", intro="none", source="url", seconds=30):
    return ("<h1>modernize43</h1>"
            "<p class=\"lead\">Film-URL einfügen. Die ersten Sekunden werden als "
            "1920×1080 mit unscharfem Hintergrund ausgegeben.</p>"
            "<form action=\"/jobs\" method=\"post\">"
            "<input type=\"url\" name=\"url\" placeholder=\"https://…/film.mp4\" "
            "value=\"%s\">"
            "%s%s%s"
            "<input type=\"number\" name=\"seconds\" min=\"1\" max=\"600\" "
            "value=\"%d\" title=\"Sekunden des Films\">"
            "<button type=\"submit\">Modernisieren</button></form>"
            % (html.escape(value),
               select("source", (("url", "Eigene URL"), ("arabella", "Arabella SD 480p")), source),
               select("logo", (("none", "Kein Logo"), ("joyn", "Joyn oben links")), logo),
               select("intro", (("none", "Ohne Vorspann"), ("joyn", "Joyn-Vorspann")), intro),
               seconds))


class Handler(BaseHTTPRequestHandler):
    server_version = "modernize43/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    @property
    def manager(self):
        return self.server.manager

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/":
            self.send_html(200, page("modernize43", form()))
            return
        if path == "/healthz":
            self.send_text(200, "ok")
            return
        match = STATUS_PATH.match(path)
        if match:
            self.handle_status(match.group(1))
            return
        match = RESULT_PATH.match(path)
        if match:
            self.handle_result(match.group(1))
            return
        match = JOB_PATH.match(path)
        if match:
            self.handle_job(match.group(1))
            return
        self.send_text(404, "nicht gefunden")

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path != "/jobs":
            self.send_text(404, "nicht gefunden")
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        fields = urllib.parse.parse_qs(body, keep_blank_values=True)
        value = (fields.get("url") or [""])[0]
        logo = (fields.get("logo") or ["none"])[0]
        intro = (fields.get("intro") or ["none"])[0]
        source = (fields.get("source") or ["url"])[0]
        try:
            seconds = int((fields.get("seconds") or ["30"])[0])
        except ValueError:
            seconds = 0
        problem = None
        if logo not in ("none", "joyn"):
            problem = "Unbekannte Logo-Option."
        elif intro not in ("none", "joyn"):
            problem = "Unbekannte Vorspann-Option."
        elif source not in ("url", "arabella"):
            problem = "Unbekannte Quelle."
        elif not 1 <= seconds <= 600:
            problem = "Die Dauer muss zwischen 1 und 600 Sekunden liegen."
        if problem:
            self.send_html(400, page("Fehler", form(value, logo, intro, source, seconds if seconds else 30) +
                                     "<div class=\"status error\">%s</div>" % problem))
            return
        candidate = ARABELLA_URL if source == "arabella" else value
        try:
            url = validate_url(candidate, self.manager.allow_private)
        except SourceError as exc:
            self.send_html(400, page("Fehler", form(value, logo, intro, source, seconds) +
                                     "<div class=\"status error\">%s</div>"
                                     % html.escape(str(exc))))
            return
        job = self.manager.create(url, logo, seconds, intro)
        self.send_response(303)
        self.send_header("Location", "/jobs/%s" % job.id)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def handle_status(self, job_id):
        job = self.manager.get(job_id)
        if job is None:
            self.send_json(404, {"error": "unbekannter Job"})
            return
        self.send_json(200, job.public())

    def handle_job(self, job_id):
        job = self.manager.get(job_id)
        if job is None:
            self.send_html(404, page("Nicht gefunden", "<h1>Job nicht gefunden</h1>"))
            return
        if job.state == "done":
            body = ("<h1>Fertig</h1>"
                    "<video controls playsinline src=\"/jobs/%s/result.mp4\"></video>"
                    "<p><a class=\"download\" href=\"/jobs/%s/result.mp4\" download>"
                    "MP4 herunterladen</a></p>"
                    "<p class=\"muted\"><a href=\"/\">Neuen Film modernisieren</a></p>"
                    % (job.id, job.id))
        elif job.state == "error":
            body = ("<h1>Fehler</h1><div class=\"status error\">%s</div>"
                    "<p><a href=\"/\">Zurück zum Formular</a></p>" % html.escape(job.message))
        else:
            body = ("<h1>Wird verarbeitet</h1>"
                    "<div class=\"status\" id=\"status\">Status: %s</div>"
                    "<p class=\"muted\">Die Seite aktualisiert sich automatisch.</p>"
                    "<script>"
                    "const poll=()=>fetch('/jobs/%s/status').then(r=>r.json()).then(d=>{"
                    "if(d.state==='done'){location.reload();return;}"
                    "if(d.state==='error'){document.getElementById('status').textContent="
                    "'Fehler: '+(d.message||'unbekannt');return;}"
                    "document.getElementById('status').textContent='Status: '+d.state;"
                    "setTimeout(poll,1000);}).catch(()=>setTimeout(poll,2000));"
                    "setTimeout(poll,500);"
                    "</script>" % (job.state, job.id))
        self.send_html(200, page("Job %s" % job.id, body))

    def handle_result(self, job_id):
        job = self.manager.get(job_id)
        if job is None:
            self.send_text(404, "unbekannter Job")
            return
        if job.state != "done" or not job.result_path or not os.path.isfile(job.result_path):
            self.send_text(409, "Ergebnis ist noch nicht verfügbar")
            return
        size = os.path.getsize(job.result_path)
        start, end = 0, size - 1
        status = 200
        header = self.headers.get("Range")
        if header:
            match = RANGE_HEADER.match(header.strip())
            if not match:
                self.send_range_error(size)
                return
            left, right = match.group(1), match.group(2)
            if left == "" and right == "":
                self.send_range_error(size)
                return
            if left == "":
                start = max(0, size - int(right))
                end = size - 1
            else:
                start = int(left)
                end = int(right) if right else size - 1
            if start > end or start >= size:
                self.send_range_error(size)
                return
            end = min(end, size - 1)
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Disposition",
                         "attachment; filename=\"modernize43-%s.mp4\"" % job.id)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        with open(job.result_path, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1 << 16, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def send_range_error(self, size):
        self.send_response(416)
        self.send_header("Content-Range", "bytes */%d" % size)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_html(self, status, body):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_text(self, status, body):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_json(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
