# Normative requirements

- R-01: `GET /` returns an HTML page with a form that has one text input named `url`, a select
  named `logo` whose options include `none` and `joyn`, and a submit control. `POST /jobs` with
  `application/x-www-form-urlencoded` and a `url` field creates a job and answers `303` with
  `Location: /jobs/<id>`. The job page `GET /jobs/<id>` exists immediately.
- R-02: The `url` value must be an absolute `http://` or `https://` URL with a non-empty host.
  Anything else, including `file:`, `ftp:`, relative paths and empty input, is rejected with HTTP
  `400` and an HTML or text response that names the problem; no job is created.
- R-03: The finished result is an MP4 file whose video stream is H.264, pixel format `yuv420p`,
  exactly 1920×1080, sample aspect ratio 1:1, with color primaries, transfer and matrix all
  `bt709`. The `moov` box appears before the `mdat` box (faststart).
- R-04: The result frame is composed of two layers. The background is the border-cropped source
  image scaled to cover 1920×1080 with its aspect ratio preserved (centre crop), blurred with a
  Gaussian-like blur and slightly darkened. The foreground is the border-cropped source image
  scaled to a height of 1080 with its display aspect ratio preserved, upscaled with Lanczos and
  mildly sharpened with contrast-adaptive sharpening, then centred horizontally. A 4:3 source
  without black borders occupies 1440×1080 with 240-pixel side bands; with cropped borders the
  width follows the cropped display aspect ratio. No black bars and no geometric distortion: the
  foreground's displayed aspect ratio is within 1% of the cropped source's display aspect ratio.
  The verification checks the bands statistically (non-black, low detail, sharp centre band of the
  expected width and position), not by reading the filter graph.
- R-05: A job has exactly one of the states `queued`, `running`, `done` or `error`.
  `GET /jobs/<id>/status` returns JSON with a `state` field and, when finished, either a result URL
  or a `message`. Jobs are processed one at a time in submission order. Unknown job ids answer
  `404`. Each job works in its own temporary directory and never writes into the source tree.
- R-06: The job page shows an HTML5 `<video controls>` element that plays the result and a download
  link to it. `GET /jobs/<id>/result.mp4` answers `200` with `Content-Type: video/mp4` and
  `Content-Disposition: attachment; filename="modernize43-<id>.mp4"`. A single-range request
  (`Range: bytes=0-99`) answers `206` with exactly 100 bytes and a `Content-Range` header. Before the
  job is done the same path answers `409`.
- R-07: The output duration is 30 seconds when the source is at least 30 seconds long, otherwise the
  full source duration, with a tolerance of 0.5 seconds. If the source has an audio stream, the
  output has exactly one AAC stereo audio stream at 192 kbit/s. If the source has no audio, the
  output has no audio stream and is still valid.
- R-08: A source is accepted only if its border-cropped display aspect ratio is narrower than 16:9
  by more than 1% relative tolerance (display aspect ratio below 16/9 divided by 1.01). Otherwise
  the job ends in state `error` with a message that contains `aspect ratio`. This accepts 4:3, 3:2,
  1:1 and portrait sources and rejects 16:9 and wider sources.
- R-09: If the download, probe or encode fails, or the job exceeds 180 seconds in total, the job
  ends in state `error`, its `message` contains the last non-empty line of the tool's stderr (at
  most 2000 characters), no result is offered, and the server keeps answering other requests.
- R-10: With default settings, a URL whose host resolves to a loopback, private, link-local or
  unspecified address is rejected by the submission with HTTP `400` and a message that contains
  `private`. When the server is started with `--allow-private-hosts`, the same URL is accepted.
- R-11: Before the composition is planned, black borders are detected by analysing sampled frames of
  the source: uniform near-black margins at the left, right, top and bottom edges are measured, and
  a detected crop is applied before scaling. At most 20% of the width and of the height may be
  removed per side. If no border is detected the frame is used unchanged. The border-cropped
  geometry, not the raw source geometry, determines the foreground width and the aspect-ratio gate.
- R-12: `POST /jobs` accepts an optional `logo` field. The value `none`, which is also the default,
  leaves the frame unchanged. The value `joyn` draws the bundled white Joyn wordmark with a dark
  drop shadow inside the top-left corner of the foreground area: 32 pixels from the top and from
  the foreground's left edge, with a width of 16% of the foreground width and never more than 20%
  of it. Any other value is rejected with HTTP `400` and no job is created. The logo is never
  fetched from the network at request time.
