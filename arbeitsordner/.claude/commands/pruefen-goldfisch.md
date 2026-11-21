---
description: Goldfisch-Prüfung eines gespeicherten Entwurfs mit frischem Kontext, nur mit dem Goldfisch-Paket.
argument-hint: "[session_id]"
---

Starte den Subagent `goldfisch` mit genau diesem Auftrag und sonst nichts:

session_id: $ARGUMENTS

Gib keine weiteren Inhalte aus diesem Gespräch an ihn weiter. Danach nur seine Rückmeldung (Zahl der Befunde je
Schwere) wiedergeben. Fehlt die session_id, nach ihr fragen und nichts starten.
