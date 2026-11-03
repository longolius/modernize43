"""URL validation and source probing."""

import ipaddress
import json
import socket
import subprocess
import urllib.parse

FFPROBE = "ffprobe"


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
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
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
        "dar": display_ratio(width, height, sar),
        "field_order": video.get("field_order") or "progressive",
        "has_audio": bool(audio),
        "duration": duration,
    }
