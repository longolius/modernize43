#!/usr/bin/env python3
"""Black-box acceptance oracle for the modernize43 public HTTP flow.

Starts the generated application, serves local fixtures, submits URLs through the
public form endpoint and verifies the produced MP4 with ffprobe and raw-frame
statistics. It never imports application modules and never reads the filter graph.
"""
import http.server
import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")
STATE_OK = {"queued", "running", "done", "error"}


def fail(message):
    print("ORACLE FAIL: " + message, file=sys.stderr)
    sys.exit(1)


def ok(label, detail=""):
    print("OK %s%s" % (label, (" " + detail) if detail else ""))


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def run(argv, timeout=120, stdout=subprocess.PIPE):
    proc = subprocess.run(argv, stdout=stdout, stderr=subprocess.PIPE, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or b"")[-2000:].decode("utf-8", "replace")
        fail("command failed (%s): %s\n%s" % (proc.returncode, " ".join(argv), tail))
    return proc.stdout


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def request(url, method="GET", data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def form_post(base, url_value):
    data = urllib.parse.urlencode({"url": url_value}).encode()
    return request(base + "/jobs", "POST", data,
                   {"Content-Type": "application/x-www-form-urlencoded"})


def wait_health(base, proc, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            fail("application exited during startup (code %s)" % proc.returncode)
        try:
            status, _, _ = request(base + "/healthz", timeout=2)
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    fail("application did not become healthy")


def start_app(port, allow_private):
    argv = [sys.executable, "-m", "modernize43", "--port", str(port)]
    if allow_private:
        argv.append("--allow-private-hosts")
    log = tempfile.TemporaryFile()
    proc = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port
    try:
        wait_health(base, proc)
    except SystemExit:
        log.seek(0)
        sys.stderr.write(log.read().decode("utf-8", "replace")[-3000:])
        raise
    return proc, base, log


def stop_app(proc):
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def submit(base, url_value):
    status, headers, body = form_post(base, url_value)
    if status != 303:
        fail("POST /jobs must answer 303, got %s: %s" % (status, body[:300]))
    location = headers.get("Location", "")
    if not location.startswith("/jobs/"):
        fail("303 Location must be /jobs/<id>, got %r" % location)
    return location.rsplit("/", 1)[-1]


def get_state(base, job_id):
    status, _, body = request(base + "/jobs/%s/status" % job_id)
    if status != 200:
        fail("status endpoint answered %s for %s" % (status, job_id))
    try:
        payload = json.loads(body.decode())
    except ValueError:
        fail("status endpoint is not JSON: %r" % body[:200])
    state = payload.get("state")
    if state not in STATE_OK:
        fail("invalid job state %r" % (state,))
    return payload


def wait_final(base, job_id, timeout=300):
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        payload = get_state(base, job_id)
        seen.add(payload["state"])
        if payload["state"] in ("done", "error"):
            return payload, seen
        time.sleep(0.3)
    fail("job %s did not finish in %ss (states seen: %s)" % (job_id, timeout, sorted(seen)))


class FixtureHandler(http.server.BaseHTTPRequestHandler):
    directory = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self.serve(False)

    def do_GET(self):
        self.serve(True)

    def serve(self, with_body):
        path = urllib.parse.urlparse(self.path).path
        if path == "/missing.mp4":
            body = b"not here"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if with_body:
                self.wfile.write(body)
            return
        if path == "/notmedia.html":
            body = b"<html><body>no media</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if with_body:
                self.wfile.write(body)
            return
        name = os.path.basename(path)
        target = os.path.join(self.directory, name)
        if not os.path.isfile(target):
            self.send_error(404)
            return
        size = os.path.getsize(target)
        start, end, status = 0, size - 1, 200
        header = self.headers.get("Range", "").strip()
        if header.startswith("bytes="):
            left, _, right = header[6:].partition("-")
            try:
                if left == "":
                    start = max(0, size - int(right))
                else:
                    start = int(left)
                    end = int(right) if right else size - 1
            except ValueError:
                start, end = 0, size - 1
            if 0 <= start <= end < size:
                status = 206
            else:
                start, end, status = 0, size - 1, 200
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if not with_body:
            return
        with open(target, "rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)


def start_fixture_server(directory):
    handler = type("Handler", (FixtureHandler,), {"directory": directory})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def make_fixtures(directory):
    clip = os.path.join(directory, "clip43.mp4")
    run([FFMPEG, "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25:duration=40",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
         "-vf", "setsar=16/15", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest", clip], timeout=180)
    silent = os.path.join(directory, "silent43.mp4")
    run([FFMPEG, "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=720x576:rate=25:duration=5",
         "-vf", "setsar=16/15", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
         "-pix_fmt", "yuv420p", silent], timeout=120)
    wide = os.path.join(directory, "wide169.mp4")
    run([FFMPEG, "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=5",
         "-vf", "setsar=1", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
         "-pix_fmt", "yuv420p", wide], timeout=120)
    bordered = os.path.join(directory, "bordered43.mp4")
    run([FFMPEG, "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=size=704x576:rate=25:duration=10",
         "-vf", "pad=720:576:8:0:black,setsar=16/15",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
         "-pix_fmt", "yuv420p", bordered], timeout=120)
    return clip, silent, wide, bordered


def probe(path):
    raw = run([FFPROBE, "-v", "error", "-print_format", "json",
               "-show_streams", "-show_format", path], timeout=60)
    return json.loads(raw.decode())


def stream(meta, kind):
    return [s for s in meta.get("streams", []) if s.get("codec_type") == kind]


def frame_rgb(path, seconds):
    raw = run([FFMPEG, "-v", "error", "-ss", str(seconds), "-i", path,
               "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], timeout=120)
    if len(raw) != 1920 * 1080 * 3:
        fail("unexpected raw frame size %d" % len(raw))
    return raw


def luma_rows(frame, step=8):
    rows = []
    row_bytes = 1920 * 3
    for y in range(0, 1080, step):
        base = y * row_bytes
        line = frame[base:base + row_bytes]
        rows.append([(line[i] * 299 + line[i + 1] * 587 + line[i + 2] * 114) // 1000
                     for i in range(0, row_bytes, 3)])
    return rows


def column_profile(rows):
    profile = []
    for x in range(1919):
        total = 0
        for row in rows:
            total += abs(row[x + 1] - row[x])
        profile.append(total / len(rows))
    return profile


def band_mean(profile, start, end):
    return sum(profile[start:end]) / float(end - start)


def band_luma(rows, start, end):
    total = 0
    count = 0
    for row in rows:
        for x in range(start, end, 4):
            total += row[x]
            count += 1
    return total / float(count)


def check_composition(path, at=10, left_expected=240, right_expected=1680,
                      width_range=(1420, 1460), border_probe=None):
    rows = luma_rows(frame_rgb(path, at))
    profile = column_profile(rows)
    center_peak = max(profile[700:1250])
    if center_peak < 2.0:
        fail("centre band has no sharp detail (peak %.2f)" % center_peak)
    left_peak = max(profile[0:200])
    right_peak = max(profile[1720:1919])
    if left_peak > 0.25 * center_peak or right_peak > 0.25 * center_peak:
        fail("side bands are not smoother than the centre "
             "(left %.2f right %.2f centre %.2f)" % (left_peak, right_peak, center_peak))
    left_window = profile[max(0, left_expected - 60):left_expected + 60]
    right_window = profile[right_expected - 60:right_expected + 60]
    left_seam = max(0, left_expected - 60) + left_window.index(max(left_window))
    right_seam = right_expected - 60 + right_window.index(max(right_window))
    if abs(left_seam - left_expected) > 16:
        fail("left seam at %d, expected %d +/- 16" % (left_seam, left_expected))
    if abs(right_seam - right_expected) > 16:
        fail("right seam at %d, expected %d +/- 16" % (right_seam, right_expected))
    width = right_seam - left_seam
    if not width_range[0] <= width <= width_range[1]:
        fail("sharp band width %d, expected %d..%d"
             % (width, width_range[0], width_range[1]))
    for name, start, end in (("left", 0, 200), ("right", 1720, 1919)):
        mean = band_luma(rows, start, end)
        if mean <= 8:
            fail("%s band is black (mean luma %.1f)" % (name, mean))
    if border_probe is not None:
        for name, edge in (("left", left_seam + border_probe),
                           ("right", right_seam - border_probe)):
            mean = band_luma(rows, edge - 4, edge + 4)
            if mean <= 8:
                fail("a black border survived %d px inside the %s seam (mean luma %.1f)"
                     % (border_probe, name, mean))
    return left_seam, right_seam, width


def check_faststart(path):
    with open(path, "rb") as handle:
        head = handle.read(8 << 20)
    moov = head.find(b"moov")
    mdat = head.find(b"mdat")
    if moov < 0:
        fail("moov box not found in the first 8 MiB")
    if 0 <= mdat < moov:
        fail("mdat precedes moov; faststart missing")


def main():
    work = tempfile.mkdtemp(prefix="modernize43-oracle-")
    fixture_server = None
    main_proc = None
    strict_proc = None
    try:
        fixture_dir = os.path.join(work, "fixtures")
        os.makedirs(fixture_dir)
        clip, silent, wide, bordered = make_fixtures(fixture_dir)
        fixture_server, fixture_port = start_fixture_server(fixture_dir)
        media = "http://127.0.0.1:%d/clip43.mp4" % fixture_port

        main_proc, base, _ = start_app(free_port(), True)

        # A-01 form and job creation
        status, _, body = request(base + "/")
        if status != 200:
            fail("GET / answered %s" % status)
        html = body.decode("utf-8", "replace")
        if 'name="url"' not in html or "<form" not in html.lower():
            fail("GET / has no url input form")
        job_id = submit(base, media)
        status, _, _ = request(base + "/jobs/%s" % job_id)
        if status != 200:
            fail("job page answered %s" % status)
        ok("A-01", "job " + job_id)

        # A-05 state machine and unknown id
        first = get_state(base, job_id)["state"]
        if first not in STATE_OK:
            fail("initial state invalid: %r" % first)
        status, _, _ = request(base + "/jobs/nope/status")
        if status != 404:
            fail("unknown job id answered %s, expected 404" % status)
        payload, seen = wait_final(base, job_id)
        if payload["state"] != "done":
            fail("main job ended in %s: %s" % (payload["state"], payload.get("message")))
        if "queued" not in seen and "running" not in seen:
            fail("no intermediate state observed: %s" % sorted(seen))
        ok("A-05", "states " + ",".join(sorted(seen)))

        # A-06 result page, download and range
        status, _, page = request(base + "/jobs/%s" % job_id)
        page_text = page.decode("utf-8", "replace").lower()
        if "<video" not in page_text or "result.mp4" not in page_text:
            fail("job page lacks video element or result link")
        result_url = base + "/jobs/%s/result.mp4" % job_id
        status, headers, blob = request(result_url)
        if status != 200:
            fail("result answered %s" % status)
        ctype = headers.get("Content-Type", "")
        if not ctype.lower().startswith("video/mp4"):
            fail("result Content-Type is %r" % ctype)
        disp = headers.get("Content-Disposition", "")
        if "attachment" not in disp.lower() or ".mp4" not in disp.lower():
            fail("result Content-Disposition is %r" % disp)
        result_path = os.path.join(work, "result.mp4")
        with open(result_path, "wb") as handle:
            handle.write(blob)
        status, rheaders, body = request(result_url, headers={"Range": "bytes=0-99"})
        if status != 206:
            fail("range request answered %s, expected 206" % status)
        if len(body) != 100:
            fail("range request returned %d bytes, expected 100" % len(body))
        if "Content-Range" not in rheaders:
            fail("range response lacks Content-Range")
        ok("A-06")

        # A-03 container and stream properties
        meta = probe(result_path)
        videos = stream(meta, "video")
        if len(videos) != 1:
            fail("expected one video stream, got %d" % len(videos))
        video = videos[0]
        checks = {
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "pix_fmt": "yuv420p",
            "sample_aspect_ratio": "1:1",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
            "color_space": "bt709",
        }
        for key, want in checks.items():
            got = video.get(key)
            if got != want:
                fail("video %s is %r, expected %r" % (key, got, want))
        check_faststart(result_path)
        ok("A-03")

        # A-04 composition
        left, right, width = check_composition(result_path)
        ok("A-04", "seams %d/%d width %d" % (left, right, width))

        # A-11 black-border crop
        bordered_job = submit(base, "http://127.0.0.1:%d/bordered43.mp4" % fixture_port)
        bordered_payload, _ = wait_final(base, bordered_job)
        if bordered_payload["state"] != "done":
            fail("bordered source ended in %s: %s"
                 % (bordered_payload["state"], bordered_payload.get("message")))
        bordered_path = os.path.join(work, "bordered-out.mp4")
        status, _, blob = request(base + "/jobs/%s/result.mp4" % bordered_job)
        if status != 200:
            fail("bordered result answered %s" % status)
        with open(bordered_path, "wb") as handle:
            handle.write(blob)
        left, right, width = check_composition(bordered_path, at=4,
                                               left_expected=256, right_expected=1664,
                                               width_range=(1392, 1424), border_probe=10)
        ok("A-11", "seams %d/%d width %d" % (left, right, width))

        # A-07 duration and audio
        duration = float(meta.get("format", {}).get("duration", "0"))
        if abs(duration - 30.0) > 0.5:
            fail("duration is %.2fs, expected 30 +/- 0.5" % duration)
        audios = stream(meta, "audio")
        if len(audios) != 1:
            fail("expected one audio stream, got %d" % len(audios))
        audio = audios[0]
        if audio.get("codec_name") != "aac":
            fail("audio codec is %r" % audio.get("codec_name"))
        if int(audio.get("channels", 0)) != 2:
            fail("audio channels is %r" % audio.get("channels"))
        rate = audio.get("bit_rate")
        if rate and not 150000 <= int(rate) <= 260000:
            fail("audio bit rate is %s" % rate)
        ok("A-07", "%.2fs" % duration)

        # silent source keeps working
        silent_url = "http://127.0.0.1:%d/silent43.mp4" % fixture_port
        silent_job = submit(base, silent_url)
        silent_payload, _ = wait_final(base, silent_job)
        if silent_payload["state"] != "done":
            fail("silent source ended in %s: %s"
                 % (silent_payload["state"], silent_payload.get("message")))
        silent_path = os.path.join(work, "silent-out.mp4")
        status, _, blob = request(base + "/jobs/%s/result.mp4" % silent_job)
        if status != 200:
            fail("silent result answered %s" % status)
        with open(silent_path, "wb") as handle:
            handle.write(blob)
        silent_meta = probe(silent_path)
        if stream(silent_meta, "audio"):
            fail("silent source produced an audio stream")
        silent_duration = float(silent_meta.get("format", {}).get("duration", "0"))
        if abs(silent_duration - 5.0) > 0.5:
            fail("silent result duration is %.2fs, expected 5 +/- 0.5" % silent_duration)
        ok("A-07b")

        # A-08 wide source rejected, HTML source errors
        wide_job = submit(base, "http://127.0.0.1:%d/wide169.mp4" % fixture_port)
        wide_payload, _ = wait_final(base, wide_job)
        if wide_payload["state"] != "error":
            fail("16:9 source ended in %s, expected error" % wide_payload["state"])
        if "aspect ratio" not in (wide_payload.get("message") or "").lower():
            fail("wide-source message lacks 'aspect ratio': %r" % wide_payload.get("message"))
        html_job = submit(base, "http://127.0.0.1:%d/notmedia.html" % fixture_port)
        html_payload, _ = wait_final(base, html_job)
        if html_payload["state"] != "error" or not html_payload.get("message"):
            fail("non-media source did not produce a readable error")
        status, _, _ = request(base + "/")
        if status != 200:
            fail("service stopped answering GET / after failures")
        ok("A-08")

        # A-02 invalid URL rejection
        for bad in ("file:///etc/passwd", "", "clip43.mp4", "ftp://example.com/a.mp4"):
            status, _, body = form_post(base, bad)
            if status != 400:
                fail("invalid url %r answered %s, expected 400" % (bad, status))
            if not body.strip():
                fail("invalid url %r produced an empty error body" % bad)
        ok("A-02")

        # A-09 media fetch failure
        missing_job = submit(base, "http://127.0.0.1:%d/missing.mp4" % fixture_port)
        missing_payload, _ = wait_final(base, missing_job)
        message = missing_payload.get("message") or ""
        if missing_payload["state"] != "error":
            fail("missing media ended in %s" % missing_payload["state"])
        if "404" not in message:
            fail("missing-media message lacks the HTTP status: %r" % message)
        status, _, _ = request(base + "/jobs/%s/result.mp4" % missing_job)
        if status == 200:
            fail("failed job offered a result file")
        status, _, _ = request(base + "/")
        if status != 200:
            fail("service unresponsive after fetch failure")
        ok("A-09")

        # A-10 private host default rejection
        strict_proc, strict_base, _ = start_app(free_port(), False)
        status, _, body = form_post(strict_base, media)
        if status != 400:
            fail("private-host url answered %s without opt-in, expected 400" % status)
        if "private" not in body.decode("utf-8", "replace").lower():
            fail("private-host rejection body does not mention 'private'")
        ok("A-10")

        print("ORACLE PASS: all acceptance criteria satisfied")
    finally:
        stop_app(main_proc)
        stop_app(strict_proc)
        if fixture_server is not None:
            fixture_server.shutdown()
            fixture_server.server_close()
        import shutil
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
