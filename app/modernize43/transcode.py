"""The ffmpeg composition: blurred cover background, sharp centred foreground."""

import os
import subprocess

from .source import SourceError, last_line

FFMPEG = "ffmpeg"
CAPTURE_SECONDS = 30
TIMEOUT_SECONDS = 180
SHARPENING = "0.35"
LOGO_MARGIN = 32
LOGO_SHARE = 0.16
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGOS = {
    "none": None,
    "joyn": os.path.join(ASSET_DIR, "joyn.png"),
}


def build_command(url, output, info, seconds=CAPTURE_SECONDS, logo="none"):
    foreground_width = int(round(1080 * info["dar"] / 2.0)) * 2
    foreground_width = max(2, min(1920, foreground_width))
    steps = []
    if info.get("field_order") in ("tt", "bb", "tb", "bt"):
        steps.append("yadif=deint=all:mode=send_frame")
    crop = info.get("crop")
    if crop:
        steps.append("crop=%d:%d:%d:%d" % (crop["w"], crop["h"], crop["x"], crop["y"]))
    steps.append("split=2[bgv][fgv]")
    head = "[0:v]" + ",".join(steps)
    background = ("[bgv]scale=iw*sar:ih:flags=lanczos,setsar=1,"
                  "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,"
                  "crop=1920:1080,boxblur=20:2,"
                  "eq=brightness=-0.06:saturation=0.75[bg]")
    foreground = ("[fgv]scale=%d:1080:flags=lanczos,setsar=1,"
                  "cas=strength=%s[fg]" % (foreground_width, SHARPENING))
    overlay = ("[bg][fg]overlay=(W-w)/2:0,setsar=1,"
               "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]")
    graph = ";".join([head, background, foreground, overlay])
    inputs = ["-i", url]
    label = "[v]"
    logo_path = LOGOS.get(logo)
    if logo_path:
        logo_width = max(160, int(round(foreground_width * LOGO_SHARE / 2.0)) * 2)
        logo_x = (1920 - foreground_width) // 2 + LOGO_MARGIN
        graph += (";[1:v]scale=%d:-1[lg];[v][lg]overlay=%d:%d[vv]"
                  % (logo_width, logo_x, LOGO_MARGIN))
        inputs += ["-i", logo_path]
        label = "[vv]"
    return [
        FFMPEG, "-y", "-v", "error", "-nostdin",
        "-rw_timeout", "30000000",
    ] + inputs + [
        "-t", str(seconds),
        "-filter_complex", graph,
        "-map", label, "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        output,
    ]


def transcode(url, output, info, timeout=TIMEOUT_SECONDS, logo="none"):
    command = build_command(url, output, info, logo=logo)
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SourceError("Die Transkodierung hat das Zeitlimit überschritten.")
    if process.returncode != 0:
        raise SourceError(last_line(process.stderr) or "ffmpeg ist fehlgeschlagen.")
    return output
