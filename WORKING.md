# Current Work

## Goal

Four changes to the skimap app: a resizable/collapsible drawer like the old
routing app, route information moved behind info icons, a styled scrollbar,
and a reworked Crux Identifier symbol set with `fall_hazard` split at 50 deg.

## Shared understanding

**Drawer.** Port the old `routing_app` Sidebar behaviour, modernised: a drag
handle on the right edge using pointer events with `setPointerCapture` (touch
and pen work, no global listener leak), `role="separator"` with arrow-key
resizing, width persisted in `localStorage`, double-click to reset. Live width
lifts into `App` so the map's `leftInset` follows it instead of using the
constant `PANEL_WIDTH`. Bounds as before: min 280, max min(1100, 58vw),
default 380. A chevron tab rides on the drag handle and collapses the drawer;
the header X stays and does the same. Collapsed state is unchanged - the
orange FAB at mid-left is the only way back.

**Info icons.** Two separate info buttons, each opening a Popover:
- on every row of the Routes list: that route's name and stats readout
  (length, straight line, detour, cost, routed in). On the row itself, not
  in a second block below - the Selected route no longer repeats its name.
- next to the "Show corridor" label: the corridor explainer paragraph.

The corridor switch and slider and the "not analysed - no terrain data"
warning stay visible. The warning is a safety caveat, not a description.

**Scrollbar.** The old app's webkit scrollbar styling - 6px, teal `#367E98`
thumb, translucent track - as a shared `scrollbarSx` in `routing/styles.ts`,
applied to the drawer's scroll container and to `RouteListSection`'s inner
list, plus `scrollbar-color` for Firefox.

**Crux Identifier.** New `steep_slope` class between `fall_hazard` and
`runout_area`; see the decision record. Icons and colours:

| Class | Icon | Colour | Marker pill |
|---|---|---|---|
| `probable_release_area` | `LandslideIcon` | red `#D32F2F` | `1 [icon]` |
| `fall_hazard` (>=50) | `TrendingDownIcon` | red `#D32F2F` | `2 [icon]` |
| `steep_slope` (30-50) | `PriorityHighIcon` | dark orange `#E65100` | `3 [icon] 38` deg |
| `runout_area` (>= 20 m) | `AirIcon` | light orange `#FFA726` | `4 [icon]` |

Degrees appear on the steep-slope pill, list row and popup only - rounded
whole degrees of `max_slope_deg`, the max over the zone. Fall hazard keeps
"Max slope" in its popup as today but no number on its pill. Marker pills
take their class colour instead of red for everything.

## Boundaries

- In: `skimap/skimap/crux.py`, `config.py`, `skimap/tests/test_crux.py`, and
  the frontend files listed below.
- Out: the router and cost surface; the corridor computation; anything in
  `routing_app/` (reference only); mobile layout beyond keeping it working -
  the drawer stays non-resizable on phones.

## Relevant paths

- `skimap/skimap/crux.py` - `CLASSES`/`RANK`, `_classify`, the module docstring
- `skimap/skimap/config.py:220` - `CRUX` thresholds
- `skimap/tests/test_crux.py` - slope fixtures around 30-35 deg need revising
- `skimap/app/frontend/src/types.ts` - `DangerClass`
- `skimap/app/frontend/src/dangerClasses.ts` - names and icons
- `skimap/app/frontend/src/theme.ts` - `CRUX_COLORS`, `PANEL_WIDTH`
- `skimap/app/frontend/src/routing/RoutePanel.tsx` - the drawer
- `skimap/app/frontend/src/routing/RouteInfo.tsx` - the shared InfoButton and
  the per-row route info popover
- `skimap/app/frontend/src/routing/SelectedRoute.tsx` - crux list, corridor
- `skimap/app/frontend/src/routing/styles.ts` - shared `scrollbarSx`
- `skimap/app/frontend/src/ui/MarkerIcons.tsx` - `cruxIcon` pill
- `skimap/app/frontend/src/map/CruxMarkers.tsx` - popup
- `skimap/app/frontend/src/map/RouteLines.tsx` - `segmentStyle`
- `skimap/app/frontend/src/map/MapView.tsx:164` - `leftInset`
- `routing_app/frontend/src/routing/Sidebar.tsx` - the drawer pattern to port

## Open questions

None.

## Current state

All four changes implemented. `config.slope_threshold` is now
`fall_threshold` (50) and `steep_threshold` (30); `crux.py` classifies and
ranks `steep_slope` between fall hazard and runout, and both slope classes
report `max_slope_deg`. Frontend has the four-class vocabulary, class-coloured
lines and marker pills, degrees on steep-slope pills and list rows, two info
popovers, the teal scrollbar, and a pointer-capture resize handle with a
collapse tab (`routing/ResizeHandle.tsx`, `routing/usePanelWidth.ts`).

Checks: 29/29 Python crux tests, 15/15 frontend tests, `tsc -b` and
`npm run build` all clean. Not yet looked at in a running browser.

## Next action

Run the app and look at it - confirm the drag feel, the popovers and the new
marker pills on a real route. Nothing else is outstanding.
