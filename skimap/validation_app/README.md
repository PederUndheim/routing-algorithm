# Korridorvalidering

A web app where outside experts judge the final corridors
(`data/corridors_final`, 1026 of them) one at a time: the best KAST class, whether the
corridor should be bigger or smaller, notes, and two flags. Each expert works
alone and blind. The app collects their answers, and the disagreements are
settled afterwards in a meeting, from the spreadsheet `admin export` writes.

```
validation_app/
  prepare.py        corridors_final -> static corridor files + track tiles
  admin.py          upload assignments, export the spreadsheet, take a backup
  assignments.json  who reviews what
  Dockerfile        the API image
  backend/          the API: server.py, store.py (Azure Tables / file),
                    verdicts.py (users, fields), snapshots.py
  frontend/         Vite + React + Leaflet; public/corridors/ from prepare.py
```

## What was decided

These are the user's choices, so they shouldn't be revisited in passing:

- **Users:** Håvard, Markus, Andreas and Finn, plus Test. They are fixed in
  `backend/verdicts.py`. One shared access code for everyone, then you pick
  your name.
- **Assignment:** set in `assignments.json`. Each user sees *only* their own
  corridors. A user who isn't in the file, or is set to `"all"`, sees all of
  them.
- **Blind:** the corridor is drawn the way the corridor review drew it, a
  PNG rendered from its GeoTIFF with the same breaks and fade. Every corridor
  is drawn in the review's blue whatever its class, so the colour says nothing. There is no route line. The class isn't
  in the static files at all (see `prepare.py`).
- **Map buttons:** picture buttons in this order: Norgeskart, Satellitt,
  Turkart, then Bratthet (on by default), Bratthet m/utløp, Spordata. Shortcuts
  are not printed on the buttons; they are listed under the keyboard icon.
- **KAST:** green, blue, red or black, each with − / 0 / +. A corridor counts
  as reviewed once it has a class.
- **Korridorstørrelse:** a judgement only, smaller / OK / bigger, with OK as
  the default. Nothing is redrawn.
- **KAST models:** *Publikumsmodell* and *Teknisk modell* links beside
  *Usikker* open the two KAST tables (`frontend/src/assets/kast/`) over the
  app. Keys are paused while one is open; Esc closes it.
- **Notes:** free text, plus *Usikker* (under the KAST class; stored as
  `doubt`) and *Problematisk for publisering*.
- **Test user:** never included in the export, and is the only user that can
  be reset.

## Keyboard

| | |
|---|---|
| ← → | previous / next (follows the list filter) |
| 1 2 3 | green − / 0 / + |
| Q W E | blue − / 0 / + |
| A S D | red − / 0 / + |
| Z X C | black − / 0 / + |
| Space | show / hide spordata |

That is all of them, by request. The keyboard icon in the panel lists them.

## Nothing gets lost

1. **In the browser:** every change is written to localStorage before it is
   sent, and sent in order until the server confirms it (`saveQueue.ts`). A
   closed tab, a dropped connection or a backend that is still starting only
   delays a change. The sidebar shows *Lagret ✓* once everything is through.
2. **On the server:** each change becomes its own row in `valhistory`, which
   is never changed or deleted, and is then merged into `valcurrent`. A retry
   carries the same opId, so it is not recorded twice. `valcurrent` can always
   be rebuilt from history.
3. **The storage account** is ZRS, so Azure keeps three copies in three
   datacentres before it acknowledges a write. It also has a delete lock.
4. **Snapshots:** the API writes the whole store to blob
   (`snapshots/validering_YYYY-MM-DD.json`), with versioning and 30 days of
   soft delete.
5. **Off-site:** `admin backup` saves everything to a JSON file on your
   machine. Run it after each working session.

## Run locally

From `skimap/`, with QGIS's Python. Nothing to install for the backend:

```powershell
$py = "C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
& $py -m validation_app.backend.server          # :8790, file store in data/validation, code "dev"
cd validation_app\frontend; npm install --ignore-scripts; npm run dev   # :5174
```

`--ignore-scripts` is needed because AppLocker blocks esbuild's install step.
`scripts/vite.mjs` points esbuild at the allowed copy in `~/.local/bin`
instead, and `package.json` pins esbuild to that copy's version (0.28.2).

Tests: `& $py -m unittest tests.test_validation_backend` (the API, over
HTTP), and `npm test` in `frontend/` (the save queue). To run the API suite
on Table Storage as well, start Azurite and set `VALIDATION_TEST_TABLES` to
its connection string.

## Data

```powershell
& $py -m validation_app.prepare                 # ~10 min, mostly track tiles
& $py -m validation_app.prepare --skip-tracks   # corridor PNGs only, ~1.5 min
```

Re-run this if `corridors_final` is rebuilt. Corridor IDs are the
`corridor_id`s from that build, so verdicts are tied to them. **Rebuilding
corridors_final after reviewing has started renumbers corridors under
existing verdicts**, so don't.

The track tiles end up in `data/validation/tracks/` and are served by the API
behind the access code. They are not in git or on Pages, because both are
public; in Azure they live on the file share (see Deploy, step 3).

## Deploy (first time)

Pages is public and so is this repository, so two things never go there:
the access code (an Azure secret) and the track tiles (`data/validation/tracks`,
ignored by git, uploaded to the Azure Files share).

1. Push to main. `deploy-validation-api.yml` builds and pushes
   `ghcr.io/pederundheim/skimap-validation-api`; its deploy job waits for
   step 6. On GitHub, open the package (profile > Packages) and set it
   **public** - it is code only.
2. Cloud Shell: `bash validation.sh storage` (storage account, tables, lock).
3. Cloud Shell: `bash azure.sh upload-url`. Then locally, in Git Bash from
   `skimap/`: `bash deploy/upload.sh "<url>" data/validation/tracks`.
4. Cloud Shell: `VALIDATION_ACCESS_CODE='<code>' bash validation.sh app`.
   It prints the API address and the admin key. Keep the admin key.
5. Check: `curl https://<api>/health`.
6. GitHub > Settings > Secrets and variables > Actions > Variables: add
   `VALIDATION_API_URL` = the API address. Re-run *Deploy skimap frontend to
   GitHub Pages*. The app: https://pederundheim.github.io/routing-algorithm/validering/
7. Locally, upload the assignment:

   ```powershell
   $env:VALIDATION_API = "<API address>"
   $env:VALIDATION_ADMIN_KEY = "<admin key>"
   & $py -m validation_app.admin assign
   ```

After that, pushes deploy themselves. Change the code with
`VALIDATION_ACCESS_CODE=... bash validation.sh code`. After rebuilding the
track tiles, upload them again (step 3); no restart is needed, the API reads
them per request.

## Admin

```powershell
& $py -m validation_app.admin assign      # after editing assignments.json
& $py -m validation_app.admin export      # -> data/validation/export/validering_<time>.xlsx
& $py -m validation_app.admin backup      # -> data/validation/backup/validering_<time>.json
```

`assignments.json`:

```json
{
  "havard":  {"regions": ["Lyngen", "Tromsø"], "ids": [412], "exclude": [101]},
  "markus":  "all"
}
```

Region names are the NVE names (`admin assign` lists them if one is
misspelled). The export has one row per corridor and one block of columns
per reviewer. After that come *Tildelt*, *Vurdert*, *Ulik klasse*, *Spenn
(trinn)* (one step is one −/0/+ notch; a whole class is three), *Ulik
størrelse* and *Flagget av noen*. Use these to sort for the meeting. Sheet
two holds every change ever made.
