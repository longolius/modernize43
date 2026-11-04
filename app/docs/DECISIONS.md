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
- D-07: Go standard library HTTP server plus `ffmpeg`/`ffprobe` subprocesses. No web framework,
  no third-party modules: the build produces one static binary, and the container needs only the
  media tools at runtime.
- D-08: Jobs are in memory, one worker, no persistence. A restart loses queued and finished jobs;
  results expire after `--retention-minutes` (60 by default).
- D-09: The submission blocks loopback, private, link-local and unspecified targets by default.
  `--allow-private-hosts` exists for local testing and is not a production mode.
- D-10: The server binds `127.0.0.1:8080` by default. Exposure to a network or the internet is out of
  scope and must be arranged outside this project.
- D-11: The service is single-user. HTTP Basic Auth is enforced at the reverse proxy, not in the
  application; the container itself must never be published without that proxy.
- D-12: Black borders are detected with `cropdetect` on at most the first five seconds and cropped
  before any scaling, capped at 20% per side. Upscaling uses Lanczos plus contrast-adaptive
  sharpening at strength 0.35 on the foreground only; denoising and grain management are not
  enabled by default because they remove texture the archive may want to keep.
- D-13: The logo is a bundled asset, not a runtime download: the white Joyn wordmark with a soft
  drop shadow, rasterised from the Wikimedia SVG, 32-pixel margin in the foreground's top-left
  corner and 16% of the foreground width. Attribution and trademark note live in
  `assets/README.md`. The dropdown is the only selector; no arbitrary logo URLs.
- D-14: The intro is a 16:9 asset and is prepended as-is, normalised to 1920×1080, square pixels,
  BT.709, the content's frame rate and AAC 48 kHz stereo. It is encoded once and joined with the
  content through the concat demuxer, so the boundary costs no extra re-encode. A silent content
  gets a silent audio track when an intro is present, otherwise the concat would fail.
- D-15: `seconds` applies to the content only; the intro adds its own length. Default 30, range
  1–600. This keeps "30 seconds of film" true when an intro is selected.
- D-16: The Arabella presets and the intro URL are fixed server-side and can be overridden with
  `MODERNIZE43_ARABELLA_URL`, `MODERNIZE43_ARABELLA_HQ_URL` and `MODERNIZE43_INTRO_URL` for the
  acceptance oracle. The UI never accepts arbitrary preset URLs.
