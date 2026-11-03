# Project goal

A single user can paste a URL to a 4:3 SD film and receive a modern 16:9 version of its first
30 seconds: the original image is scaled to full height at 1920×1080 without distortion, the side
bands are filled with a blurred and darkened copy of the same image, and the result is playable in
the browser and downloadable as an MP4 file.

The value is a repeatable "modernize" step for an archive of old 4:3 material that must not look
stretched or cropped.

## Current scope

- One direct HTTP(S) media URL per job, entered in a web form.
- Only the first 30 seconds of the source are transcoded; a shorter source yields the whole source.
- Output is 1920×1080 H.264 in MP4 with AAC audio, correct SAR, BT.709 tags and faststart.
- The job page shows queued, running, done or failed.
- A finished job offers an HTML5 player and a download link.
- Invalid URLs, non-4:3-and-narrower sources and failed downloads produce a readable error.
- The service refuses to fetch private, loopback or link-local addresses unless started with an
  explicit opt-in flag.

## Excluded

- Batch processing or multiple files per job.
- Transcoding beyond the first 30 seconds.
- Page scraping or platform integrations (YouTube and similar); the input is a direct media URL.
- Subtitle, chapter or metadata preservation beyond what the container carries by default.
- AI upscaling, denoising filters beyond the background blur, or creative regrading.
- User accounts, authentication, multi-user isolation.
- Persistence across restarts; jobs and results are ephemeral.
- Container images, reverse proxy, TLS and remote deployment.
- Mobile-specific layout beyond a readable single-column page.
