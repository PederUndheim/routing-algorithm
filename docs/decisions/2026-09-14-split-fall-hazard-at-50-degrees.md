# Split fall hazard at 50 degrees

Date: 2026-09-14

## Context

`fall_hazard` covered every slope at or above 30 degrees with no upper cap.
On Norwegian ski terrain that is most of what is worth skiing, so a large
share of a typical route was drawn full-danger red and carried a fall-hazard
marker. The signal that a stretch is genuinely no-fall terrain was lost in
the ground that is merely steep.

The map's line colour comes from `segment.class`, and a segment carries no
slope value - only a Crux entry does, via `max_slope_deg`.

## Decision

Split the old band into two Danger classes at 50 degrees:

- `fall_hazard` - slope >= 50 deg, no upper cap. Keeps its icon.
- `steep_slope` - 30 <= slope < 50 deg. New class, new icon and colour.

`steep_slope` is ranked immediately below `fall_hazard` and immediately above
`runout_area`, which is where the old single class sat. Ranking behaviour is
therefore unchanged: anything the old `fall_hazard` outranked, the pair still
outranks.

## Alternatives

- **Split in the frontend only**, labelling markers by `max_slope_deg`. Cheap,
  no API change - but segments have no slope value, so the line under a 35 deg
  traverse would still be drawn full-danger red while its own marker said
  otherwise. Rejected: the line is the thing you read while moving.
- **Rank `steep_slope` below `runout_area`**, on the argument that a runout
  area is a live avalanche exposure and a 35 deg slope on its own is milder.
  Rejected: it silently changes what existing routes report, and the user
  asked to keep the previous hierarchy.

## Consequences

- The API's Danger class vocabulary grows from three to four. Anything holding
  stored `/crux` responses sees a class it did not before.
- `config.CRUX` grows a second slope threshold; the single `slope_threshold`
  is gone.
- Python tests that built ~30-35 deg slope fixtures now describe `steep_slope`;
  fixtures and expectations were updated so all four classes stay covered.
- The frontend colour scale gains a fourth entry, and Crux marker pills take
  their own class colour rather than red for every class - otherwise a runout
  marker was a red pill sitting on an orange line.
