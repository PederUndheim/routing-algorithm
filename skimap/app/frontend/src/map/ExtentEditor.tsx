import { useEffect, useMemo } from "react";
import { Marker } from "react-leaflet";
import { divIcon } from "leaflet";
import type { LeafletEvent, Marker as LeafletMarker } from "leaflet";
import type { LineString } from "geojson";

import { geodesicLength } from "../routes/routeList";
import { nearestOnLine, pointAtDistance } from "../routes/snap";
import type { Extent } from "../types";

/** The shortest stretch the handles can be pulled together to, so they can
 *  never cross or sit on top of each other. */
const MIN_EXTENT_M = 10;

const handleIcon = (color: string) =>
  divIcon({
    html: `<div style="width:14px;height:14px;border-radius:50%;background:white;border:3px solid ${color};box-shadow:0 1px 4px rgba(0,0,0,0.5);box-sizing:border-box"></div>`,
    className: "",
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });

type ExtentEditorProps = {
  /** The Route's line while an extent is being edited, else null. */
  line: LineString | null;
  extent: Extent | null;
  color: string;
  /** Called as a handle is dragged, so the coloured stretch follows live. */
  onChange: (extent: Extent) => void;
  onCancel: () => void;
};

/** Editing the stretch a Crux colours: a handle at each end, dragged along
 *  the route - wherever the pointer goes, the handle stays on the nearest
 *  point of the line. Escape gives up. The stretch itself is drawn by the
 *  route lines, from the extent as it is dragged. */
const ExtentEditor = ({ line, extent, color, onChange, onCancel }: ExtentEditorProps) => {
  const active = line !== null && extent !== null;
  const icon = useMemo(() => handleIcon(color), [color]);
  const length = useMemo(() => (line ? geodesicLength(line.coordinates) : 0), [line]);

  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, onCancel]);

  if (!line || !extent) return null;

  const drag = (end: keyof Extent) => (e: LeafletEvent) => {
    const marker = e.target as LeafletMarker;
    const { lat, lng } = marker.getLatLng();
    const along = nearestOnLine(line, { lat, lng }).distance_m;
    const next =
      end === "start_m"
        ? { ...extent, start_m: Math.min(along, extent.end_m - MIN_EXTENT_M) }
        : { ...extent, end_m: Math.max(along, extent.start_m + MIN_EXTENT_M) };
    const clamped = {
      start_m: Math.max(next.start_m, 0),
      end_m: Math.min(next.end_m, length),
    };
    // Held on the line under the pointer, not wherever it was let go.
    const snapped = pointAtDistance(line, clamped[end]);
    marker.setLatLng([snapped.lat, snapped.lng]);
    onChange(clamped);
  };

  return (
    <>
      {(["start_m", "end_m"] as const).map((end) => {
        const at = pointAtDistance(line, extent[end]);
        return (
          <Marker
            key={end}
            position={[at.lat, at.lng]}
            icon={icon}
            draggable
            pane="markers"
            zIndexOffset={2000}
            title={end === "start_m" ? "Start of the stretch" : "End of the stretch"}
            eventHandlers={{ drag: drag(end), dragend: drag(end) }}
          />
        );
      })}
    </>
  );
};

export default ExtentEditor;
