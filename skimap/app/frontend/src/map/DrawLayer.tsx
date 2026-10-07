import { useEffect, useMemo, useState } from "react";
import { Marker, Pane, Polyline, useMap, useMapEvents } from "react-leaflet";
import { divIcon } from "leaflet";
import type { LatLngTuple, Marker as LeafletMarker } from "leaflet";

import type { LatLng } from "../types";
import { COLORS } from "../theme";

const handle = (size: number, fill: string, border: string, opacity = 1) =>
  divIcon({
    html: `<div style="width:${size}px;height:${size}px;box-sizing:border-box;border-radius:50%;background:${fill};border:2px solid ${border};opacity:${opacity};box-shadow:0 1px 3px rgba(0,0,0,0.45)"></div>`,
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });

// The line has a direction - the Crux Identifier reads it in the order it
// was drawn - so its two ends say which is which, in the start and end
// markers' colours.
const startHandle = handle(16, COLORS.teal, "white");
const endHandle = handle(16, COLORS.orange, "white");
const vertexHandle = handle(14, "white", COLORS.orange);
const midpointHandle = handle(10, "white", COLORS.orange, 0.7);

/** A drag in progress: one point moved, or a new one pulled out of the
 *  middle of a segment. Kept here until it is let go, so the line follows
 *  the pointer without the whole app re-rendering on every move. */
type Preview = { kind: "move" | "insert"; index: number; at: LatLng };

const applyPreview = (points: readonly LatLng[], preview: Preview | null): LatLng[] => {
  if (!preview) return [...points];
  const next = [...points];
  if (preview.kind === "move") next[preview.index] = preview.at;
  else next.splice(preview.index, 0, preview.at);
  return next;
};

const toLatLng = (e: { target: unknown }): LatLng => {
  const { lat, lng } = (e.target as LeafletMarker).getLatLng();
  return { lat, lng };
};

type DrawLayerProps = {
  active: boolean;
  points: readonly LatLng[];
  onChange: (points: LatLng[]) => void;
};

/** The line being drawn, and every way to shape it: a click on the map adds
 *  a point at the end, a point can be dragged, a click on one removes it,
 *  and dragging the faint handle halfway along a segment bends the line
 *  there with a new point. Shown only while drawing. */
const DrawLayer = ({ active, points, onChange }: DrawLayerProps) => {
  const map = useMap();
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    if (!active) return;
    // Two quick clicks are two points, not a zoom.
    map.doubleClickZoom.disable();
    const el = map.getContainer();
    el.classList.add("drawing");
    return () => {
      map.doubleClickZoom.enable();
      el.classList.remove("drawing");
    };
  }, [map, active]);

  useMapEvents({
    click: (e) => {
      if (active) onChange([...points, { lat: e.latlng.lat, lng: e.latlng.lng }]);
    },
  });

  // Stable between renders on purpose: react-leaflet moves a marker whenever
  // its position prop is a new object, and that would snap a handle back
  // out from under the pointer in the middle of a drag.
  const vertices = useMemo(
    () => points.map((p) => [p.lat, p.lng] as LatLngTuple),
    [points]
  );
  const midpoints = useMemo(
    () =>
      points.slice(1).map((p, i) => {
        const q = points[i];
        return [(p.lat + q.lat) / 2, (p.lng + q.lng) / 2] as LatLngTuple;
      }),
    [points]
  );

  // Always mounted, like the map's other panes; only what is in it comes and goes.
  if (!active || points.length === 0) return <Pane name="draft" style={{ zIndex: 650 }} />;

  const shown = applyPreview(points, preview).map((p) => [p.lat, p.lng] as LatLngTuple);
  const last = points.length - 1;

  return (
    <Pane name="draft" style={{ zIndex: 650 }}>
      <Polyline
        positions={shown}
        interactive={false}
        pathOptions={{ color: COLORS.orange, weight: 4, dashArray: "8 8" }}
      />

      {midpoints.map((position, i) => (
        <Marker
          key={`mid-${i}`}
          position={position}
          icon={midpointHandle}
          draggable
          eventHandlers={{
            drag: (e) => setPreview({ kind: "insert", index: i + 1, at: toLatLng(e) }),
            dragend: (e) => {
              setPreview(null);
              onChange(applyPreview(points, { kind: "insert", index: i + 1, at: toLatLng(e) }));
            },
          }}
        />
      ))}

      {vertices.map((position, i) => (
        <Marker
          key={`pt-${i}`}
          position={position}
          icon={i === 0 ? startHandle : i === last ? endHandle : vertexHandle}
          draggable
          eventHandlers={{
            // Leaflet sends no click after a drag, so this is a real click.
            click: () => onChange(points.filter((_, j) => j !== i)),
            drag: (e) => setPreview({ kind: "move", index: i, at: toLatLng(e) }),
            dragend: (e) => {
              setPreview(null);
              onChange(applyPreview(points, { kind: "move", index: i, at: toLatLng(e) }));
            },
          }}
        />
      ))}
    </Pane>
  );
};

export default DrawLayer;
