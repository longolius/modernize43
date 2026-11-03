"""The ffmpeg composition, the optional intro and the final concatenation."""

import os
import subprocess

from .source import SourceError, last_line, probe_has_audio

FFMPEG = "ffmpeg"
CAPTURE_SECONDS = 30
TIMEOUT_SECONDS = 180
SHARPENING = "0.35"
LOGO_MARGIN = 32
LOGO_SHARE = 0.16
INTRO_WIDTH = 1920
INTRO_HEIGHT = 1080
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGOS = {
    "none": None,
    "joyn": os.path.join(ASSET_DIR, "joyn.png"),
}
VIDEO_ENCODE = [
    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
    "-pix_fmt", "yuv420p",
    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
]
AUDIO_ENCODE = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def build_command(url, output, info, seconds=CAPTURE_SECONDS, logo="none",
                  with_silence=False):
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
    index = 1
    label = "[v]"
    logo_path = LOGOS.get(logo)
    if logo_path:
        logo_width = max(160, int(round(foreground_width * LOGO_SHARE / 2.0)) * 2)
        logo_x = (1920 - foreground_width) // 2 + LOGO_MARGIN
        graph += (";[%d:v]scale=%d:-1[lg];[v][lg]overlay=%d:%d[vv]"
                  % (index, logo_width, logo_x, LOGO_MARGIN))
        inputs += ["-i", logo_path]
        index += 1
        label = "[vv]"
    audio_map = "0:a:0?"
    if with_silence:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_map = "%d:a:0" % index
    return ([FFMPEG, "-y", "-v", "error", "-nostdin", "-rw_timeout", "30000000"]
            + inputs
            + ["-t", str(seconds),
               "-filter_complex", graph,
               "-map", label, "-map", audio_map]
            + VIDEO_ENCODE + AUDIO_ENCODE
            + ["-movflags", "+faststart", output])


def encode_intro(url, output, fps, has_audio, timeout=TIMEOUT_SECONDS):
    inputs = ["-i", url]
    audio_map = "0:a:0?"
    extra = []
    if not has_audio:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_map = "1:a:0"
        extra = ["-shortest"]
    graph = ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
             "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%s,"
             "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709"
             % (INTRO_WIDTH, INTRO_HEIGHT, INTRO_WIDTH, INTRO_HEIGHT, fps))
    command = ([FFMPEG, "-y", "-v", "error", "-nostdin"]
               + inputs
               + ["-map", "0:v:0", "-map", audio_map, "-vf", graph]
               + VIDEO_ENCODE + AUDIO_ENCODE
               + extra + ["-movflags", "+faststart", output])
    _run(command, timeout, "Der Vorspann konnte nicht verarbeitet werden.")


def concat(intro_path, content_path, output, timeout=TIMEOUT_SECONDS):
    listing = output + ".concat.txt"
    escaped = [path.replace("'", "'\\''") for path in (intro_path, content_path)]
    with open(listing, "w", encoding="utf-8") as handle:
        for path in escaped:
            handle.write("file '%s'\n" % path)
    command = [FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
               "-i", listing, "-c", "copy", "-movflags", "+faststart", output]
    _run(command, timeout, "Vorspann und Film konnten nicht verbunden werden.")
    try:
        os.unlink(listing)
    except OSError:
        pass


def _run(command, timeout, message):
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SourceError("Die Transkodierung hat das Zeitlimit überschritten.")
    if process.returncode != 0:
        raise SourceError(last_line(process.stderr) or message)


def transcode(url, output, info, timeout=TIMEOUT_SECONDS, logo="none",
              seconds=CAPTURE_SECONDS, intro_url=None):
    if not intro_url:
        _run(build_command(url, output, info, seconds=seconds, logo=logo),
             timeout, "ffmpeg ist fehlgeschlagen.")
        return output
    content = output + ".content.mp4"
    intro = output + ".intro.mp4"
    try:
        _run(build_command(url, content, info, seconds=seconds, logo=logo,
                           with_silence=not info["has_audio"]),
             timeout, "ffmpeg ist fehlgeschlagen.")
        encode_intro(intro_url, intro, info.get("fps") or "25/1",
                     probe_has_audio(intro_url), timeout)
        concat(intro, content, output, timeout)
    finally:
        for temporary in (content, intro):
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return output
