import { Polyline } from "react-leaflet";
import type { LatLngTuple, PathOptions } from "leaflet";
import type { LineString } from "geojson";

import { shelfOf } from "../crux/assessment";
import type { Route } from "../routes/routeList";
import { sliceLine } from "../routes/snap";
import type { CruxSegment, Extent } from "../types";
import { COLORS, CRUX_COLORS, dangerColor } from "../theme";

// Lines are immutable once in the list, so each is converted once. A Route
// uploaded from a GPS recording can be tens of thousands of points, and a
// fresh array every render would have Leaflet re-project all of them.
const latLngCache = new WeakMap<LineString, LatLngTuple[]>();

/** A GeoJSON line's [lng, lat] as Leaflet's [lat, lng]. */
export const latLngsOf = (line: LineString): LatLngTuple[] => {
  let latLngs = latLngCache.get(line);
  if (!latLngs) {
    latLngs = line.coordinates.map(([lng, lat]) => [lat, lng] as LatLngTuple);
    latLngCache.set(line, latLngs);
  }
  return latLngs;
};

/** One colour per segment, the same one its Crux marker is drawn in: red
 *  for steep ground that turns out to be a release area or a fall hazard,
 *  dark orange where it is only steep, light orange for the lesser Runout
 *  area. */
const segmentStyle = (segment: CruxSegment): PathOptions =>
  segment.class === "no_data"
    // Dashed as well as grey, so it cannot be read as a paler green.
    ? { color: CRUX_COLORS.noData, dashArray: "8 10" }
    : { color: dangerColor(segment) };

const latLngsAlong = (route: Route, extent: Extent): LatLngTuple[] =>
  sliceLine(route.line, extent.start_m, extent.end_m).map(
    ([lng, lat]) => [lat, lng] as LatLngTuple
  );

/** What the user has done to a Route's colouring, as lines to draw over
 *  the analysis: an identified Crux whose extent was edited has its old area
 *  cleared to green and its new extent coloured in its own colour; one placed
 *  by hand colours the stretch it was given. None of it while the Crux is
 *  deleted or not kept, as with its marker - the analysis shows through. */
const overridesOf = (route: Route) => {
  const cleared: LatLngTuple[][] = [];
  const coloured: { id: string; color: string; positions: LatLngTuple[] }[] = [];
  for (const crux of route.cruxes) {
    if (!crux.extent || shelfOf(crux) !== "active") continue;
    if (crux.source === "identified" && crux.area) cleared.push(latLngsAlong(route, crux.area));
    coloured.push({ id: crux.id, color: dangerColor(crux), positions: latLngsAlong(route, crux.extent) });
  }
  return { cleared: cleared.filter((p) => p.length >= 2), coloured: coloured.filter((c) => c.positions.length >= 2) };
};

type RouteLinesProps = {
  routes: readonly Route[];
  selectedId: string | null;
  /** Map clicks are taken - a point is being picked or a line drawn - so a
   *  click on a Route is not a selection. */
  clickTaken: boolean;
  onSelect: (id: string) => void;
};

/** Every visible Route: the Selected route at full strength and on top, the
 *  rest thinner and faded behind it. A Route the Crux Identifier has run on
 *  is drawn from its segments; one it has not stays teal.
 *
 * Keyed on the selection as well as the id, so a Route that becomes selected
 * is added afresh. Leaflet stacks vectors in the order they were added, and
 * re-adding is the only way to lift one above a line it overlaps. */
const RouteLines = ({ routes, selectedId, clickTaken, onSelect }: RouteLinesProps) => {
  const visible = routes.filter((r) => r.visible);
  const ordered = [
    ...visible.filter((r) => r.id !== selectedId),
    ...visible.filter((r) => r.id === selectedId),
  ];

  return (
    <>
      {ordered.flatMap((route) => {
        const selected = route.id === selectedId;
        const key = `${route.id}:${selected}`;
        const stroke: PathOptions = { weight: selected ? 6 : 3, opacity: selected ? 1 : 0.55 };
        const eventHandlers = {
          // While a point is picked or a line drawn the click belongs to
          // that - it reaches the map as well, and is used there.
          click: () => {
            if (!clickTaken) onSelect(route.id);
          },
        };

        const base = route.crux ? (
          route.crux.segments.map((segment, i) => (
            <Polyline
              key={`${key}:${i}`}
              positions={latLngsOf(segment.line)}
              pathOptions={{ ...segmentStyle(segment), ...stroke }}
              eventHandlers={eventHandlers}
            />
          ))
        ) : (
          <Polyline
            key={key}
            positions={latLngsOf(route.line)}
            pathOptions={{ color: COLORS.teal, ...stroke }}
            eventHandlers={eventHandlers}
          />
        );

        // Added after the analysis, so what the user set lies over whatever
        // the terrain made of that ground - every clearing before any colour,
        // so one Crux's new extent is never wiped by another's old area.
        const { cleared, coloured } = overridesOf(route);
        const overrides = [
          ...cleared.map((positions, i) => (
            <Polyline
              key={`${key}:cleared:${i}`}
              positions={positions}
              pathOptions={{ color: CRUX_COLORS.none, ...stroke }}
              eventHandlers={eventHandlers}
            />
          )),
          ...coloured.map(({ id, color, positions }) => (
            <Polyline
              key={`${key}:crux:${id}`}
              positions={positions}
              pathOptions={{ color, ...stroke }}
              eventHandlers={eventHandlers}
            />
          )),
        ];

        return [base, ...overrides];
      })}
    </>
  );
};

export default RouteLines;
