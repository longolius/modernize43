# Deployment: modernize43 on svm-ai

Stand: 2026-11-03. Diese Datei ist Betriebsdokumentation, keine normative Spezifikation —
die gepinnte Spec liegt unter `app/docs/` und bleibt unverändert.

## Wo

| Feld | Wert |
| --- | --- |
| Host | `svm-ai` (öffentlich `49.13.203.142`) |
| Tailnet | SvM / `headscale.svonm.de`, Node-IP `100.64.0.18` |
| DNS im Tailnet | `svm-ai.svonm.internal` |
| Verzeichnis | `/opt/containers/modernize43` |
| Image | `modernize43:0.1.0` |
| Container | `modernize43`, `restart: unless-stopped` |
| Portbindung | `100.64.0.18:8095 -> 8080/tcp` |

Erreichbar ausschließlich über das SvM-Tailnet:

- <http://svm-ai.svonm.internal:8095/>
- <http://100.64.0.18:8095/>

Nicht erreichbar (verifiziert am 2026-11-03):

- öffentliche IP `49.13.203.142:8095` → Connection refused
- Longolius-Tailnet (HAL `100.64.0.8`) → Timeout, weil anderes Headscale

Die Zugriffskontrolle ist die Bindung an die Tailscale-Adresse. Es gibt keine
Authentifizierung in der App; sie darf nicht an `0.0.0.0` gebunden werden.

## Update

Der Gateway-Container hat kein `rsync`. Der Deploy läuft deshalb als tar über SSH:

```sh
cd /home/openclaw/.openclaw/workspace/modernize43
tar -C app -czf - . | ssh svm-ai \
  'mkdir -p /opt/containers/modernize43 && tar -C /opt/containers/modernize43 -xzf -'
ssh svm-ai 'cd /opt/containers/modernize43 && docker compose up -d --build'
```

`docker compose` ist auf dem Host vorhanden (v5.6.1). Ein Neustart des Containers
verliert laufende und fertige Jobs; Ergebnisse liegen nur in `/tmp` im Container.

## Prüfen

```sh
ssh svm-ai 'docker ps --filter name=modernize43 \
  --format "{{.Names}} {{.Status}} {{.Ports}}"'
ssh svm-ai 'curl -sS -o /dev/null -w "%{http_code}\n" \
  http://100.64.0.18:8095/healthz'
```

Erwartet: Container `Up`, Ports `100.64.0.18:8095->8080/tcp`, Health `200`.
Zusätzlich von außen prüfen, dass die öffentliche IP den Port **nicht** öffnet.

## End-to-End-Nachweis (2026-11-03)

Im Container wurde ein 4:3-Testsignal (720×576, SAR 16:15) über HTTP verarbeitet.
Ergebnis mit `ffprobe` geprüft:

- `1920x1080`, `sample_aspect_ratio=1:1`
- `color_primaries=bt709`, `color_transfer=bt709`, `color_space=bt709`
- H.264 + AAC stereo
- `duration=30.000000`

Der Test lief in einem separaten Check-Container mit `--allow-private-hosts` gegen
einen Fixture-Server im selben Docker-Netz. Der produktive Container läuft ohne
dieses Flag und blockiert private Ziele.

## Grenzen

- Ein File pro Job, nur die ersten 30 Sekunden.
- Media-URLs, die ins SvM-Netz zeigen, werden vom Default-Schutz blockiert.
  Wer das braucht, muss bewusst `--allow-private-hosts` setzen — dann ist die
  SSRF-Grenze weg und die App darf nur noch im Tailnet stehen.
- Keine Persistenz, kein Auth, keine horizontalen Skalierung.
