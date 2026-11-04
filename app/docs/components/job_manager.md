---
component_id: job_manager
---

**Komponente:** C-02

Der Job-Manager hält Jobs im Speicher, führt sie nacheinander in einem Worker aus und macht
ihren Zustand abfragbar.

```mermaid
flowchart LR
  A["<b>1 · Annehmen</b><br/>validierter Auftrag<br/>Job im Zustand queued"] --> B["<b>2 · Ausführen</b><br/>ein Worker, FIFO<br/>running und Ergebnisdatei"] --> C["<b>3 · Abschließen</b><br/>Zustand und Meldung<br/>done oder error"]
```

## Zweck

Genau eine Aufgabe: Reihenfolge, Isolation und Lebenszyklus der Jobs. Sie legt pro Job ein
eigenes temporäres Verzeichnis an, begrenzt die Laufzeit und übersetzt Fehler aus Quellen-
prüfung und Transkodierung in einen lesbaren Jobzustand. Sie führt selbst kein ffmpeg aus.

## Schnittstelle

```text
Create(url, logo, seconds, intro) -> JobID
Get(jobID)                        -> Job | nicht gefunden
Job.Public()                      -> {id, state, message?, result_url?}
```

`Create` kehrt sofort zurück; die Verarbeitung läuft asynchron. Ein unbekannter Job ist ein
eigener Fehlerfall und wird von der Web-Schnittstelle als `404` ausgegeben.

## Ablauf

| Schritt | Aktion | Ergebnis |
| --- | --- | --- |
| 1 | Auftrag annehmen und Verzeichnis anlegen | Job `queued` |
| 2 | Quelle prüfen, transkodieren, Ergebnis ablegen | Job `running`, danach Datei |
| 3 | Zustand setzen und Meldung begrenzen | Job `done` oder `error` |

## Regeln

| ID | Regel |
| --- | --- |
| JOB-01 | Genau ein Worker verarbeitet Jobs in Ankunftsreihenfolge; kein Job startet, bevor der vorherige beendet ist. |
| JOB-02 | Jeder Job hat genau einen Zustand aus `queued`, `running`, `done`, `error`; Fehlermeldungen sind auf 2000 Zeichen begrenzt und enthalten die letzte Werkzeugzeile. |
| JOB-03 | Jeder Job arbeitet in einem eigenen temporären Verzeichnis, hält das Gesamtbudget von 180 Sekunden ein und hinterlässt bei Fehlern kein Ergebnis. |

## Links

- [[COMPONENTS]] — Komponentenindex
- [[ARCHITECTURE]] — öffentlicher Fluss und Abhängigkeiten
- [[transcoder]] — führt die Medienverarbeitung aus
- [[source_inspector]] — liefert Geometrie und Machbarkeit
