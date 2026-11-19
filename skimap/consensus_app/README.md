# Konsensusmøte

The app for the two consensus meetings after the corridor validation. The
experts and the chair go through each corridor together and settle on one
KAST class (the same twelve steps as the validation), the corridor size, whether it is problematic to publish
(and what should change), and a common comment.

It is a separate app from `validation_app`, with its own API, storage and
access code. It reads the experts' verdicts live from the validation data and
has no way to change them (see *Kept apart* below).

```
consensus_app/
  prepare.py        validation assignments -> backend/meetings.json (the meetings' corridors)
  admin.py          export the spreadsheet, take a backup
  Dockerfile        the API image
  backend/          server.py, store.py (Azure Tables / file), consensus.py
                    (meetings, fields), experts.py (read-only validation), snapshots.py
  frontend/         Vite + React + Leaflet; corridor images from validation_app's public/
```

## What was decided

These are the user's choices (2026-11-18). Don't revisit them in passing.

- **Meetings, not users:** the start page shows the meetings.
  - *23. november*: Håvard, Finn and Andreas, on Andreas's 517 corridors.
  - *30. november*: Håvard, Finn and Halvor, on Halvor's 507.
  - Markus reviewed the same corridors as Halvor but is left out.
  - There are no names. Everyone in the meeting can edit, others' changes
    show within a few seconds, and the last write to a field wins.
  - *Prøvemøte* is for trying the app. It is the only meeting that can be
    reset and is never exported.
- **Layout:** map on the left. The middle column shows the three experts'
  verdicts, one card each, with a *Kompakt / Full* switch at the top that
  each browser remembers. *Kompakt*: a label such as "Blå −", tags for
  size, Usikker and Problematisk, and the note. *Full*: the validation app's
  own panel as the expert left it (twelve KAST steps, Usikker,
  Korridorbredde, note, Problematisk), scaled down so all three fit without
  scrolling. A green *Enige* shows when they agree; there is no list of why
  they don't (tried and dropped). The right column is the validation
  sidebar with the consensus in place of the verdict.
- **Consensus fields:** KAST class on the validation app's twelve-step
  control (four classes, each − 0 +), corridor size, *Problematisk for
  publisering* with *Hva bør endres*, and a common comment. No *Usikker*.
- **Videre arbeid** (between size and comments): three toggles for what to
  do with the corridor later - *Legg til nytt mellompunkt* and *Endre
  sluttpunkt*, each with a box for where, and *Til to turer*, with where
  each tour goes and its class (twelve-step). Shown as tags in the list and
  as columns in the export.
- **Agreed from the start:** a corridor counts as agreed when all three
  experts have:
  - set a class, and the same main class
  - left the size at OK
  - not ticked *Problematisk* or *Usikker*

  Notes and the −/0/+ step don't count. An agreed corridor is shown as done
  with that class and the middle of the experts' three steps (hatched,
  *Enige fra start*). Changing anything on it stores the class
  with the change. ← → skip agreed corridors (unless the list is filtered to
  *Enige fra start*); they stay in the list and open on a click. The progress
  bar shows three parts: *enige fra start*,
  *avklart i møtet* and *gjenstår*.
- **No class colouring:** corridors are violet as in the validation, and the
  routing model's class is not shown anywhere.
- **Order:** plain corridor order. The list filters by status, region and
  Problematisk.

## Keyboard

| | |
|---|---|
| ← → | previous / next (follows the list filter, skips corridors the experts agreed on) |
| 1 2 3 | green − / 0 / + |
| Q W E | blue − / 0 / + |
| A S D | red − / 0 / + |
| Z X C | black − / 0 / + |
| Space | show / hide spordata |

## Kept apart from the validation app

- **Own storage:** the account `skimapkonsensus` holds the tables
  `konscurrent` and `konshistory`. Each change becomes a history row first,
  as in the validation app.
- **Experts, read-only:** the experts' verdicts come from `valcurrent`
  through a SAS that only has read permission on that one table. The app has
  no key to the validation account. Locally it reads the newest
  `data/validation/backup/validering_*.json`.
- **Corridor files:** `prepare.py` only reads
  `validation_app/assignments.json` and the corridor index. The frontend
  takes the corridor images from `validation_app/frontend/public` at build
  time.
- **Track tiles:** read from the same file share folder.

## Run locally

From `skimap/`, with QGIS's Python:

```powershell
$py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
& $py -m validation_app.admin backup           # fresh expert verdicts (needs VALIDATION_API/KEY), optional
& $py -m consensus_app.backend.server          # :8791, file store in data/consensus, code "dev"
cd consensus_app\frontend; npm install --ignore-scripts; npm run dev   # :5175
```

Tests: `& $py -m unittest tests.test_consensus_backend`, and `npm test` in
`frontend/` (the agreement rule).

If the validation assignments change, run `& $py -m consensus_app.prepare`
and push.

## Deploy (first time)

1. Push to main. `deploy-consensus-api.yml` builds and pushes
   `ghcr.io/pederundheim/skimap-consensus-api`. On GitHub, open the package
   (profile > Packages) and set it to **public**. It is code only.
2. In Cloud Shell, run `bash consensus.sh storage`.
3. In Cloud Shell, run `CONSENSUS_ACCESS_CODE='<code>' bash consensus.sh app`.
   It prints the API address and the admin key. Keep the admin key.
4. Check it with `curl https://<api>/health`. It should say
   `"experts": "validation-tables"`.
5. In GitHub, go to Settings > Secrets and variables > Actions > Variables
   and add `CONSENSUS_API_URL` = the API address. Then re-run *Deploy skimap
   frontend to GitHub Pages*. The app is at
   https://pederundheim.github.io/routing-algorithm/konsensus/

After that, pushes deploy themselves. The read-only SAS expires at the end
of 2027; `bash consensus.sh sas` renews it.

## Admin

```powershell
$env:CONSENSUS_API = "<API address>"
$env:CONSENSUS_ADMIN_KEY = "<admin key>"
& $py -m consensus_app.admin export      # -> data/consensus/export/konsensus_<time>.xlsx
& $py -m consensus_app.admin backup      # -> data/consensus/backup/konsensus_<time>.json
```

The export has one sheet per meeting and one row per corridor: status,
consensus, each expert's verdict, and why they differ. The last sheet holds
every change. Take a backup after each meeting.
