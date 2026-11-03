# modernize43

Turn 4:3 SD footage into 16:9 without distortion: the source is scaled to full height at
1920×1080 and centred, while a blurred, slightly darkened copy fills the side bands.

## Run

```sh
python3 -m modernize43 --port 8080
```

Open <http://127.0.0.1:8080>, paste a direct `http://` or `https://` URL to a 4:3 media file
and submit. The first 30 seconds are transcoded and offered as an in-page player and a download.

Requires Python 3.11+ and `ffmpeg`/`ffprobe` on `PATH`. No third-party Python packages.

## Flags

- `--host` (default `127.0.0.1`), `--port` (default `8080`)
- `--allow-private-hosts` permits loopback and private targets (tests only; default off)
- `--retention-minutes` (default `60`) how long results stay downloadable

## Limits

One file per job, first 30 seconds only, no accounts, no persistence. Sources at or wider than
16:9 are rejected rather than cropped.
