import { Polyline } from "react-leaflet";
import type { LatLngTuple, PathOptions } from "leaflet";
import type { LineString } from "geojson";

import type { Route } from "../routes/routeList";
import type { PickMode, SegmentClass } from "../types";
import { COLORS, CRUX_COLORS } from "../theme";

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

/** One red for every Danger class: which one it is, the Crux marker says. */
const segmentStyle = (segmentClass: SegmentClass): PathOptions => {
  switch (segmentClass) {
    case "none":
      return { color: CRUX_COLORS.none };
    case "no_data":
      // Dashed as well as grey, so it cannot be read as a paler green.
      return { color: CRUX_COLORS.noData, dashArray: "8 10" };
    default:
      return { color: CRUX_COLORS.danger };
  }
};

type RouteLinesProps = {
  routes: readonly Route[];
  selectedId: string | null;
  pickMode: PickMode;
  onSelect: (id: string) => void;
};

/** Every visible Route: the Selected route at full strength and on top, the
 *  rest thinner and faded behind it. A Route the Crux Identifier has run on
 *  is drawn from its segments; one it has not stays teal.
 *
 * Keyed on the selection as well as the id, so a Route that becomes selected
 * is added afresh. Leaflet stacks vectors in the order they were added, and
 * re-adding is the only way to lift one above a line it overlaps. */
const RouteLines = ({ routes, selectedId, pickMode, onSelect }: RouteLinesProps) => {
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
          // While a start or end is being picked the click belongs to the
          // picker - it reaches the map as well, and sets the point there.
          click: () => {
            if (!pickMode) onSelect(route.id);
          },
        };

        if (!route.crux) {
          return (
            <Polyline
              key={key}
              positions={latLngsOf(route.line)}
              pathOptions={{ color: COLORS.teal, ...stroke }}
              eventHandlers={eventHandlers}
            />
          );
        }

        return route.crux.segments.map((segment, i) => (
          <Polyline
            key={`${key}:${i}`}
            positions={latLngsOf(segment.line)}
            pathOptions={{ ...segmentStyle(segment.class), ...stroke }}
            eventHandlers={eventHandlers}
          />
        ));
      })}
    </>
  );
};

export default RouteLines;
