# Decisions and assumptions

- D-01: Input is a direct HTTP(S) media URL. Page scraping and platform integrations are excluded,
  so `ffmpeg` reads the URL itself and only the needed bytes are fetched.
- D-02: The first 30 seconds are encoded, never more. This keeps the first run fast and makes the
  duration contract checkable.
- D-03: Output is 1920×1080 even though SD carries no extra detail; 1080p is the expected modern
  delivery size. H.264 CRF 20, `yuv420p`, `+faststart`; audio AAC 192 kbit/s stereo.
- D-04: The background is a cover-scaled, centre-cropped, blurred and slightly darkened copy of the
  source, not a stretched copy, so it never shows a distorted image even as a backdrop.
- D-05: The foreground keeps the source display aspect ratio, including the non-square SAR of PAL
  SD, and is scaled to height 1080. This is the only way to avoid the classic 720×576 squeeze.
- D-06: Sources at or wider than 16:9 are rejected instead of cropped. The project is about narrow
  archive material; cropping or re-framing a widescreen source would be a different product.
- D-07: Python standard library HTTP server plus `ffmpeg`/`ffprobe` subprocesses. No web framework
  and no third-party Python packages, so the tool runs anywhere the media tools exist.
- D-08: Jobs are in memory, one worker, no persistence. A restart loses queued and finished jobs;
  results expire after `--retention-minutes` (60 by default).
- D-09: The submission blocks loopback, private, link-local and unspecified targets by default.
  `--allow-private-hosts` exists for local testing and is not a production mode.
- D-10: The server binds `127.0.0.1:8080` by default. Exposure to a network or the internet is out of
  scope and must be arranged outside this project.
- D-11: The service is single-user with no authentication. It must not be exposed publicly in this
  revision.
