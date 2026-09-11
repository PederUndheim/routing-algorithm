import { useEffect, useRef } from "react";
import { Marker, Popup, useMap } from "react-leaflet";
import type { Marker as LeafletMarker } from "leaflet";

import { DANGER_CLASS_NAMES } from "../dangerClasses";
import { km, stretchLength } from "../format";
import type { Route } from "../routes/routeList";
import type { Crux, MapFocus } from "../types";
import { cruxIcon } from "../ui/MarkerIcons";

/** How bad it gets, for the two classes where one number says it. */
const severity = (crux: Crux): string | null => {
  if (crux.max_pra_percent !== undefined) {
    return `Max release probability: ${Math.round(crux.max_pra_percent)}%`;
  }
  if (crux.max_slope_deg !== undefined) return `Max slope: ${Math.round(crux.max_slope_deg)}°`;
  return null;
};

const CruxPopup = ({ crux }: { crux: Crux }) => {
  const extra = severity(crux);
  return (
    <Popup>
      <strong>
        {crux.number}. {DANGER_CLASS_NAMES[crux.class]}
      </strong>
      <br />
      From start: {km(crux.distance_m)}
      <br />
      Zone length: {stretchLength(crux.length_m)}
      {extra && (
        <>
          <br />
          {extra}
        </>
      )}
    </Popup>
  );
};

const markerKey = (routeId: string, number: number) => `${routeId}:${number}`;

type CruxMarkersProps = {
  routes: readonly Route[];
  selectedId: string | null;
  focus: MapFocus | null;
};

/** A numbered marker at every Crux of every visible, analysed Route, with a
 *  popup saying what it is. Hiding a Route hides its Cruxes with it. The
 *  Selected route's sit on top at full size; the rest recede.
 *
 * Also answers a focus on one Crux - from the drawer's list - by moving the
 * map to it and opening its popup, which is why it keeps its markers. */
const CruxMarkers = ({ routes, selectedId, focus }: CruxMarkersProps) => {
  const map = useMap();
  const markers = useRef(new Map<string, LeafletMarker>());

  useEffect(() => {
    if (focus?.kind !== "crux") return;
    map.setView([focus.position.lat, focus.position.lng], Math.max(map.getZoom(), 15));
    // Absent when its Route is hidden: then the map still goes there.
    markers.current.get(markerKey(focus.routeId, focus.number))?.openPopup();
  }, [map, focus]);

  return (
    <>
      {routes
        .filter((route) => route.visible && route.crux)
        .flatMap((route) => {
          const selected = route.id === selectedId;
          return route.crux!.cruxes.map((crux) => {
            const key = markerKey(route.id, crux.number);
            return (
              <Marker
                key={key}
                ref={(marker) => {
                  if (marker) markers.current.set(key, marker);
                  else markers.current.delete(key);
                }}
                position={[crux.position.lat, crux.position.lng]}
                icon={cruxIcon(crux.number, crux.class, selected)}
                zIndexOffset={selected ? 1000 : 0}
                pane="cruxes"
              >
                <CruxPopup crux={crux} />
              </Marker>
            );
          });
        })}
    </>
  );
};

export default CruxMarkers;
