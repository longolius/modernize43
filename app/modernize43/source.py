"""URL validation, source probing and black-border detection."""

import ipaddress
import json
import os
import re
import socket
import subprocess
import urllib.parse

FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"
CROP_PATTERN = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")

INTRO_URL = os.environ.get("MODERNIZE43_INTRO_URL",
                           "https://hal.longolius.cc/joynintro.m4v")
ARABELLA_URL = os.environ.get("MODERNIZE43_ARABELLA_URL",
                              "https://hal.longolius.cc/arabella%20-%20SD%20480p.mov")


class SourceError(Exception):
    """A readable problem with the submitted source."""


def last_line(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def display_ratio(width, height, sar):
    num, den = 1, 1
    if sar and ":" in sar:
        left, right = sar.split(":", 1)
        try:
            num, den = int(left), int(right)
        except ValueError:
            num, den = 1, 1
    if num <= 0 or den <= 0:
        num, den = 1, 1
    return (width * num) / float(height * den)


def validate_url(raw, allow_private):
    if raw is None or not raw.strip():
        raise SourceError("Bitte eine URL angeben.")
    value = raw.strip()
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise SourceError("Nur http:// und https:// sind erlaubt.")
    if not parts.hostname:
        raise SourceError("Die URL enthält keinen Host.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise SourceError("Die URL enthält einen ungültigen Port.")
    if not allow_private:
        try:
            infos = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror:
            raise SourceError("Der Host %s konnte nicht aufgelöst werden." % parts.hostname)
        for info in infos:
            try:
                address = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if (address.is_private or address.is_loopback or address.is_link_local
                    or address.is_unspecified or address.is_reserved
                    or address.is_multicast):
                raise SourceError("Private Netzwerkadressen sind nicht erlaubt.")
    return value


def detect_crop(url, timeout=45):
    """Measure uniform near-black margins on a short sample."""
    command = [FFMPEG, "-v", "info", "-nostdin", "-ss", "1", "-t", "4",
               "-i", url, "-vf", "cropdetect=24:2:0", "-f", "null", "-"]
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    if process.returncode != 0:
        return None
    matches = CROP_PATTERN.findall(process.stderr or "")
    if not matches:
        return None
    width, height, x, y = (int(value) for value in matches[-1])
    if width <= 0 or height <= 0:
        return None
    return {"w": width, "h": height, "x": x, "y": y}


def _acceptable_crop(crop, width, height):
    if crop is None:
        return None
    if crop["w"] >= width and crop["h"] >= height:
        return None
    right = width - crop["w"] - crop["x"]
    bottom = height - crop["h"] - crop["y"]
    for margin, total in ((crop["x"], width), (right, width),
                          (crop["y"], height), (bottom, height)):
        if margin < 0 or margin > total * 0.2:
            return None
    if crop["w"] <= 0 or crop["h"] <= 0:
        return None
    return crop


def probe(url, timeout=60):
    command = [FFPROBE, "-v", "error", "-rw_timeout", "30000000",
               "-print_format", "json", "-show_streams", "-show_format", url]
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SourceError("Die Quelle antwortet nicht innerhalb von %d Sekunden." % timeout)
    if process.returncode != 0:
        raise SourceError(last_line(process.stderr) or "Die Quelle konnte nicht gelesen werden.")
    try:
        data = json.loads(process.stdout or "{}")
    except ValueError:
        raise SourceError("ffprobe lieferte keine gültige Ausgabe.")
    videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not videos:
        raise SourceError("Die Quelle enthält keine Videospur.")
    video = videos[0]
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise SourceError("Die Bildabmessungen der Quelle sind unbekannt.")
    sar = video.get("sample_aspect_ratio") or "1:1"
    crop = _acceptable_crop(detect_crop(url, timeout=min(45, timeout)), width, height)
    cropped_width = crop["w"] if crop else width
    cropped_height = crop["h"] if crop else height
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    fps = video.get("avg_frame_rate") or video.get("r_frame_rate") or "25/1"
    if fps in ("0/0", "0", ""):
        fps = "25/1"
    duration = 0.0
    try:
        duration = float(data.get("format", {}).get("duration")
                         or video.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "width": width,
        "height": height,
        "sar": sar,
        "crop": crop,
        "dar": display_ratio(cropped_width, cropped_height, sar),
        "field_order": video.get("field_order") or "progressive",
        "has_audio": bool(audio),
        "fps": fps,
        "duration": duration,
    }

def probe_has_audio(url, timeout=30):
    command = [FFPROBE, "-v", "error", "-rw_timeout", "30000000",
               "-print_format", "json", "-show_streams", url]
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SourceError("Der Vorspann antwortet nicht innerhalb von %d Sekunden." % timeout)
    if process.returncode != 0:
        raise SourceError(last_line(process.stderr) or "Der Vorspann konnte nicht gelesen werden.")
    try:
        data = json.loads(process.stdout or "{}")
    except ValueError:
        raise SourceError("ffprobe lieferte für den Vorspann keine gültige Ausgabe.")
    return any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))
