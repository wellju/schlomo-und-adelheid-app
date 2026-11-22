---
description: Schickt eine Fallvignette und eine Schlussfolgerung an den Goldfisch, um Anker- und Bestätigungseffekte aufzudecken (Intervision und Supervision).
argument-hint: "[session_id]"
---

Fehlt eine `session_id` (aus $ARGUMENTS oder der laufenden /intervision bzw. /supervision), danach fragen und
nichts starten. Gebraucht werden zwei Dinge in den Worten der Psychologin und anonymisiert: die Fallvignette
(höchstens wenige Sätze) und ihre Schlussfolgerung. Stehen sie schon in $ARGUMENTS (`Vignette:`,
`Schlussfolgerung:`), nimm sie unverändert und frag nicht nach; sonst lass sie sie nennen.

Starte den Subagent `goldfisch` mit genau diesem Auftrag und sonst nichts:

```
Hypothese, session_id: <session_id>
Vignette: <Vignette>
Schlussfolgerung: <Schlussfolgerung>
```

Gib keine weiteren Inhalte aus diesem Gespräch an ihn weiter. Danach nur seine Rückmeldung (Zahl der Befunde je
Schwere) wiedergeben; die Befunde stehen im Protokoll.
