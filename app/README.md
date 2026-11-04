# modernize43

Turn 4:3 SD footage into 16:9 without distortion: the source is scaled to full height at
1920×1080 and centred, while a blurred, slightly darkened copy fills the side bands.

## Run

```sh
go build -o modernize43 .
./modernize43 --port 8080
```

Open <http://127.0.0.1:8080>, paste a direct `http://` or `https://` URL to a 4:3 media file
and submit. Options: source preset (Arabella SD 480p), logo overlay (Joyn, top-left of the
4:3 area), intro (Joyn, 16:9, prepended in full) and the content duration in seconds
(default 30, range 1–600).

Requires Go 1.22+ to build and `ffmpeg`/`ffprobe` on `PATH` at runtime. No third-party Go
modules.

## Flags

- `--host` (default `127.0.0.1`), `--port` (default `8080`)
- `--allow-private-hosts` permits loopback and private targets (tests only; default off)
- `--retention-minutes` (default `60`) how long results stay downloadable

## Limits

One file per job, configurable opening section, no accounts, no persistence. Sources at or
wider than 16:9 are rejected rather than cropped.
