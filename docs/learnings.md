# Learnings aus Build und Deployment

Stand: 2026-11-03. Betriebs- und Prozesswissen, bewusst außerhalb von `app/docs/`:
Die gepinnte Spec und ihre Approval-Bindung bleiben unverändert. Wenn ein Punkt
normativ werden soll, braucht er eine neue Docs-Revision mit neuer Freigabe.

## Transcoding

1. **BT.709-Tags muss man an zwei Stellen setzen.** `-color_primaries`,
   `-color_trc` und `-colorspace` als Output-Optionen reichten mit libx264 nicht:
   `ffprobe` zeigte nur `color_space`, `color_primaries` und `color_transfer`
   blieben leer. Zusätzlich `setparams=color_primaries=bt709:color_trc=bt709:
   colorspace=bt709` als letzten Filterknoten setzen. Danach sind alle drei
   Felder gesetzt.

2. **AAC-192k ist bei 44,1 kHz nicht 192k.** Der native AAC-Encoder landete bei
   ~141 kbit/s. Mit `-ar 48000` werden 191,9 kbit/s erreicht. Wer eine Bitraten-
   zusage in die Spec schreibt, muss die Samplerate mit festlegen.

3. **SAR ist der eigentliche Verzerrungsfalle bei PAL-SD.** 720×576 mit SAR 16:15
   ergibt DAR 4:3. `scale=-2:1080` allein skaliert auf 1350×1080 und behält
   SAR 16:15; mit `setsar=1` danach wäre das Bild 6 % zu schmal. Richtig ist,
   die Zielbreite aus der DAR zu rechnen (1440) und dann `setsar=1` zu setzen.

## HTTP-Quellen und ffmpeg

4. **ffmpeg über HTTP braucht einen Range-fähigen Server.** Gegen
   `python3 -m http.server` (HTTP/1.0, kein `Range`) bricht ffmpeg mit
   „Stream ends prematurely" ab und schreibt eine leere Datei. nginx/CDNs sind
   unproblematisch. Für Orakel und lokale Tests deshalb immer HTTP/1.1 plus
   Byte-Ranges implementieren — oder einen echten Webserver als Fixture nutzen.
   Damit ist auch klar: Ein vermeintlicher App-Fehler war ein Test-Harness-Fehler.
   Erst die Testumgebung auf Produktionsniveau bringen, dann die App verdächtigen.

5. **`-t 30` nach `-i`** begrenzt zuverlässig die Ausgabedauer und stoppt das
   Demuxen früh; kein separater Download nötig.

## Verifikation

6. **Bildkomposition nicht über Median-Detail prüfen.** Testbilder haben große
   einfarbige Flächen; der Median der Spaltenprofile ist dann fast null, obwohl
   das Bild scharf ist. Robust ist der **Peak** des Spaltenprofils plus die
   Kantenposition: Der Übergang Hintergrund/Vordergrund liegt bei 4:3-Quellen
   exakt bei x=240 und x=1680. Damit lassen sich Breite, Zentrierung und Blur
   in einem Durchgang prüfen.

7. **Farb-/Formatzusagen getrennt prüfen.** `ffprobe`-Felder für Codec, SAR,
   Primaries, Transfer und Matrix sind einzeln assertierbar und billiger als
   Pixelvergleiche.

## DCE-Prozess

8. **Approval ist an den Source-Commit gebunden.** Schon eine Orakel-Korrektur
   (Fixture-Server) erzeugt eine neue Revision und damit eine neue Freigabe,
   obwohl die Markdown-Spec identisch ist. Für die Planung: Test-Harness früh
   fertigstellen, bevor man die erste Freigabe einholt. Bundle-Hash und
   Index-Hash bleiben dabei gleich, der Source-Commit nicht.

9. **Build-Records und Betriebsdokus gehören nicht unter `app/docs/`.** Jede
   nicht im Index deklarierte Datei dort lässt den nächsten Preflight mit
   `undeclared docs file` scheitern. Repo-weite `docs/` und `build-records/`
   sind der richtige Ort.

10. **Erst App-Fehler, dann Spec-Fehler.** Die zwei echten Build-Fails waren
    Generatorfehler (Farb-Tags, Audio-Bitrate). Die Spec war korrekt; sie
    deshalb nicht aufweichen.

## Deployment

11. **Portbindung ist die Zugriffskontrolle.** `-p 100.64.0.18:8095:8080` bindet
    nur die Tailscale-Adresse. `0.0.0.0:8095` wäre öffentlich, weil Docker
    veröffentlichte Ports an einer inaktiven/umgangenen Host-Firewall vorbeiführt.
    Nach jedem Deploy die öffentliche IP gegenprüfen.

12. **Zwei Tailnets, keine Route dazwischen.** Der Gateway-Node hängt im
    Longolius-Netz und kann den SvM-Node nicht erreichen. Verifikation deshalb
    auf dem Zielhost selbst; „von außen nicht erreichbar" vom Gateway aus prüfen.

13. **Kein `rsync` im Gateway-Container.** Deploy per `tar | ssh`. Und:
    `pkill -f "http.server 8899"` in einem SSH-Kommando killt die eigene Shell,
    weil das Muster in der Kommandozeile steht — Port über `fuser -k` freigeben.

14. **Testcontainers sauber aufräumen.** Check-Container und Fixture-Netz nach
    dem Nachweis entfernen; der produktive Container bleibt allein übrig.
