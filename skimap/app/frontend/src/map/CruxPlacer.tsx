import { useEffect, useState } from "react";
import { CircleMarker, useMap, useMapEvents } from "react-leaflet";
import type { LineString } from "geojson";

import { nearestOnLine } from "../routes/snap";
import type { LatLng } from "../types";
import { COLORS } from "../theme";

type CruxPlacerProps = {
  /** The Selected route's line while Add crux is pressed, else null. */
  line: LineString | null;
  /** A spot already chosen, waiting in the Add crux form. */
  pending: LatLng | null;
  onPlace: (spot: { position: LatLng; distance_m: number }) => void;
  onCancel: () => void;
};

const dot = { color: "white", weight: 2, fillColor: COLORS.orange, fillOpacity: 1 };

/** Placing a Crux by hand: while it is on, the cursor changes, a dot rides
 *  along the route under the pointer, and a click puts the Crux on the
 *  nearest point of the route - wherever on the map it lands. Escape gives
 *  up. Renders only the dots. */
const CruxPlacer = ({ line, pending, onPlace, onCancel }: CruxPlacerProps) => {
  const map = useMap();
  const [hover, setHover] = useState<LatLng | null>(null);
  const active = line !== null;

  useEffect(() => {
    if (!active) {
      setHover(null);
      return;
    }
    const el = map.getContainer();
    el.classList.add("placing-crux");
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      el.classList.remove("placing-crux");
      window.removeEventListener("keydown", onKey);
    };
  }, [map, active, onCancel]);

  useMapEvents({
    mousemove: (e) => {
      if (line) setHover(nearestOnLine(line, e.latlng).position);
    },
    mouseout: () => setHover(null),
    click: (e) => {
      if (line) onPlace(nearestOnLine(line, { lat: e.latlng.lat, lng: e.latlng.lng }));
    },
  });

  const shown = pending ?? (active ? hover : null);
  if (!shown) return null;
  return (
    <CircleMarker
      center={[shown.lat, shown.lng]}
      radius={7}
      pathOptions={dot}
      interactive={false}
      pane="markers"
    />
  );
};

export default CruxPlacer;
