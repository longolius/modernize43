# Acceptance criteria

All criteria are verified by the independent oracle O-01 (`tests/acceptance.py`), which drives the
public HTTP interface only and inspects the produced file with `ffprobe` and raw-frame statistics.
The composition check is statistical by design; it does not read the filter graph.

- A-01: Given a running service and a reachable 4:3 MP4 fixture, when the user opens `GET /` and
  posts its URL to `/jobs`, then the form contains an input named `url`, selects named `logo`, `intro` and `source`
  with a `joyn`/`arabella` option, and a number input named `seconds` with value 30, the response is `303` with a `Location` of `/jobs/<id>`, and
  `GET /jobs/<id>` answers `200`.
- A-02: Given the same service, when the user posts `file:///etc/passwd`, an empty value and a
  relative path, then each request answers `400`, the body names the problem, and no job page is
  created.
- A-03: Given a finished job, when the result is probed, then the video stream is H.264,
  `yuv420p`, 1920×1080, SAR `1:1`, primaries/transfer/matrix `bt709`, and the `moov` box precedes
  `mdat` in the file.
- A-04: Given a finished job from a 4:3 source, when a frame from the middle of the clip is
  extracted as RGB24, then the outer 200-pixel bands are non-black (mean luma above 8) and smoother
  than the centre (mean horizontal detail below 50% of the centre band), and the sharp band spans
  1300–1500 pixels horizontally and is centred at 960 ± 60 pixels.
- A-05: Given a submitted job, when the status endpoint is polled immediately and until completion,
  then every observed state is one of `queued`, `running`, `done`, `error`, the job reaches `done`,
  and an unknown id answers `404`.
- A-06: Given a finished job, when the job page and the result path are requested, then the page
  contains a `<video` element and a download link ending in `result.mp4`, the file response is
  `200` with `Content-Type: video/mp4` and an attachment filename ending in `.mp4`, and a request
  with `Range: bytes=0-99` answers `206` with 100 bytes and a `Content-Range` header.
- A-07: Given a 40-second 4:3 source with audio, when its job finishes, then the result duration is
  30.0 ± 0.5 seconds and it contains exactly one AAC stereo stream at about 192 kbit/s. Given a
  source without audio, the result still succeeds and has no audio stream.
- A-08: Given a 16:9 source and a source URL that returns HTML instead of media, when each job
  finishes, then both end in state `error`; the first message contains `aspect ratio`, and the
  second message is non-empty. The service still answers `GET /` afterwards.
- A-09: Given a source URL that the fixture server answers with HTTP 404 for the media request,
  when the job finishes, then the state is `error`, the message contains the HTTP status or the
  tool's error line, no result path answers `200`, and the server remains responsive.
- A-10: Given a service started without the opt-in flag, when the user posts a URL pointing at
  `127.0.0.1`, then the response is `400` with `private` in the body and no job exists. Given a
  service started with `--allow-private-hosts`, the same URL is accepted and reaches `done`.
- A-11: Given a 720×576 source with an 8-pixel black bar on the left and on the right (content
  704×576, SAR 16:15), when its job finishes, then the sharp band is 1408 ± 16 pixels wide and
  centred at 960 ± 40, the side bands are non-black and smoother than the centre, and no column
  within 8 pixels inside either seam is near-black (mean luma above 8).
- A-12: Given the same 4:3 source, when one job is submitted with `logo=none` and one with
  `logo=joyn`, then both finish and, in a frame taken at 10 seconds, the mean absolute luma
  difference in the top-left foreground area (x 260–500, y 40–150) is at least 2 and at least four
  times the difference measured in a control area lower in the frame (x 260–500, y 700–810).
- A-13: Given a 3-second 16:9 intro fixture and a 4:3 content fixture, when a job is submitted with
  `intro=joyn` and `seconds=5`, then the result duration is 8.0 ± 0.7 seconds, a frame at 1 second
  has a blue-dominant mean (blue above 60 and above 1.5× red), and a frame at 5 seconds is not
  blue-dominant.
- A-14: Given the same content, when a job is submitted with `seconds=4` and no intro, then the
  result duration is 4.0 ± 0.5 seconds.
- A-15: Given the content preset is overridden to a local 640×480 fixture, when a job is submitted
  with `source=arabella`, an empty `url` and `seconds=4`, then the job reaches `done`, the result is
  1920×1080 and the duration is 4.0 ± 0.5 seconds.

## Regelbindung der Komponenten

Jede Komponentenregel ist an mindestens ein Abnahmekriterium gebunden. Regeln ohne Bindung
werden nicht in die Spezifikation aufgenommen.

| Regel | Kriterien |
| --- | --- |
| WEB-01 | A-01, A-02, A-08, A-14, A-15 |
| WEB-02 | A-01, A-05, A-06, A-09 |
| WEB-03 | A-06 |
| JOB-01 | A-05 |
| JOB-02 | A-05, A-08, A-09 |
| JOB-03 | A-09 |
| TRC-01 | A-03 |
| TRC-02 | A-04, A-11 |
| TRC-03 | A-07, A-13, A-14 |
| TRC-04 | A-12 |
| SRC-01 | A-02, A-10 |
| SRC-02 | A-08 |
| SRC-03 | A-11 |
- A-16: Given the HQ preset is overridden to a local 768×576 fixture, when a job is submitted with
  `source=arabella_hq`, an empty `url` and `seconds=4`, then the job reaches `done`, the result is
  1920×1080 and the duration is 4.0 ± 0.5 seconds.
