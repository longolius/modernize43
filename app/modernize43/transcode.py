"""The ffmpeg composition: blurred cover background, sharp centred foreground."""

import subprocess

from .source import SourceError, last_line

FFMPEG = "ffmpeg"
CAPTURE_SECONDS = 30
TIMEOUT_SECONDS = 180


def build_command(url, output, info, seconds=CAPTURE_SECONDS):
    foreground_width = int(round(1080 * info["dar"] / 2.0)) * 2
    foreground_width = max(2, min(1920, foreground_width))
    if info.get("field_order") in ("tt", "bb", "tb", "bt"):
        head = "[0:v]yadif=deint=all:mode=send_frame,split=2[bgv][fgv]"
    else:
        head = "[0:v]split=2[bgv][fgv]"
    background = ("[bgv]scale=1920:1080:force_original_aspect_ratio=increase,"
                  "crop=1920:1080,boxblur=20:2,"
                  "eq=brightness=-0.06:saturation=0.75[bg]")
    foreground = "[fgv]scale=%d:1080,setsar=1[fg]" % foreground_width
    overlay = "[bg][fg]overlay=(W-w)/2:0,setsar=1,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
    graph = ";".join([head, background, foreground, overlay])
    return [
        FFMPEG, "-y", "-v", "error", "-nostdin",
        "-rw_timeout", "30000000",
        "-i", url,
        "-t", str(seconds),
        "-filter_complex", graph,
        "-map", "[v]", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        output,
    ]


def transcode(url, output, info, timeout=TIMEOUT_SECONDS):
    command = build_command(url, output, info)
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SourceError("Die Transkodierung hat das Zeitlimit überschritten.")
    if process.returncode != 0:
        raise SourceError(last_line(process.stderr) or "ffmpeg ist fehlgeschlagen.")
    return output
