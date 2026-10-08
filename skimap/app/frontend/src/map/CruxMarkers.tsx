import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Marker, Popup, useMap, useMapEvent } from "react-leaflet";
import { latLngBounds } from "leaflet";
import type { Marker as LeafletMarker } from "leaflet";

import {
  isCritical,
  isDecided,
  overallOf,
  ratingOf,
  shelfOf,
  verdictOf,
} from "../crux/assessment";
import { cruxTitle, dangerName } from "../dangerClasses";
import { km, stretchLength } from "../format";
import type { Route } from "../routes/routeList";
import { markerSpot } from "../routes/snap";
import type { CruxEntry, LatLng, MapFocus } from "../types";
import { cruxIcon, cruxIconSize } from "../ui/MarkerIcons";
import RatingMark from "../ui/RatingMark";
import { clusterCruxes, clusterLabel } from "./clusterCruxes";
import type { CruxCluster } from "./clusterCruxes";

/** A Crux as it is drawn. Whether the user rated it critical overall
 *  travels with it for the popups, and so does where its marker stands:
 *  `MARKER_LEAD_M` before an identified Crux, so it is seen in time to weigh
 *  it up before walking into it, but exactly on one the user placed or
 *  moved. */
type ShownCrux = CruxEntry & { critical: boolean; markerPosition: LatLng };

/** How bad it gets: the steepest ground in the area, and the highest
 *  release probability where the area is a release area at all. */
const severity = (crux: CruxEntry): string[] => {
  const lines: string[] = [];
  if (crux.max_slope_deg !== undefined) {
    lines.push(`Max slope: ${Math.round(crux.max_slope_deg)}°`);
  }
  if (crux.max_pra_percent !== undefined) {
    lines.push(`Max release probability: ${Math.round(crux.max_pra_percent)}%`);
  }
  return lines;
};

/** How long a stretch the Crux colours: the user's extent where it has
 *  one, else the area the analysis found. */
const areaLength = (crux: CruxEntry): number =>
  crux.extent ? crux.extent.end_m - crux.extent.start_m : crux.length_m;

const CruxPopup = ({ crux }: { crux: ShownCrux }) => {
  const rating = overallOf(crux);
  return (
    <Popup>
      <strong>
        {crux.number}. {cruxTitle(crux)}
      </strong>
      {rating && (
        <>
          {" "}
          <strong
            style={{
              color: ratingOf(rating).color,
              display: "inline-flex",
              alignItems: "center",
              gap: 3,
              verticalAlign: "middle",
            }}
          >
            <RatingMark rating={rating} size={16} />
            {ratingOf(rating).overall}
          </strong>
        </>
      )}
      <br />
      From start: {km(crux.distance_m)}
      {/* A hand-placed Crux is a point unless it was given a stretch to colour. */}
      {areaLength(crux) > 0 && (
        <>
          <br />
          Area length: {stretchLength(areaLength(crux))}
        </>
      )}
      {severity(crux).map((line) => (
        <span key={line}>
          <br />
          {line}
        </span>
      ))}
      {crux.source === "manual" && (
        <>
          <br />
          Placed by hand
        </>
      )}
    </Popup>
  );
};

/** What a cluster holds, worst first, so the reason it is drawn the colour
 *  it is comes first, and how many of them have been assessed. Zooming in is
 *  what separates them, and the popup says so rather than leaving it to be
 *  guessed. */
const ClusterPopup = ({ cluster }: { cluster: CruxCluster<ShownCrux> }) => (
  <Popup>
    <strong>
      Cruxes {clusterLabel(cluster)} ({cluster.members.length})
    </strong>
    <br />
    From start: {km(cluster.head.distance_m)}
    <br />
    <em>
      Worst: {dangerName(cluster.worst)}
      {cluster.worst.critical && " (critical)"}
    </em>
    {severity(cluster.worst).map((line) => (
      <span key={line}>
        <br />
        {line}
      </span>
    ))}
    <br />
    {cluster.members.filter(isDecided).length} of {cluster.members.length} assessed
    <br />
    Zoom in to separate them.
  </Popup>
);

const markerKey = (routeId: string, number: number) => `${routeId}:${number}`;

type CruxMarkersProps = {
  routes: readonly Route[];
  selectedId: string | null;
  focus: MapFocus | null;
  /** A single Crux's marker was clicked, so its questions should open. */
  onCruxClick: (routeId: string, cruxId: string) => void;
};

/** A marker at every active Crux of every visible Route - critical or not
 *  yet assessed - with a popup saying what it is. An identified Crux's
 *  stands 30 m before it, along the line. Hiding a Route hides its Cruxes with it, and one
 *  judged not critical, or deleted, is not drawn at all. The Selected
 *  route's sit on top at full size; the rest recede.
 *
 * Where markers would overlap they are drawn as one, carrying the worst of
 * what it holds and the span of Crux numbers it covers - so a dense route
 * reads at any zoom, and nothing is dropped, only stacked. Clustering is
 * per Route: two Routes crossing keep their own markers, because a marker
 * belongs to a line you are deciding about.
 *
 * Also answers a focus on one Crux - from the drawer's list - by moving the
 * map to it and opening its popup. That zoom usually breaks the cluster it
 * was in, so the focus is held until a marker for it exists. */
const CruxMarkers = ({ routes, selectedId, focus, onCruxClick }: CruxMarkersProps) => {
  const map = useMap();
  const markers = useRef(new Map<string, LeafletMarker>());
  const pending = useRef<MapFocus | null>(null);
  const [zoom, setZoom] = useState(() => map.getZoom());

  useMapEvent("zoomend", () => setZoom(map.getZoom()));

  // A Crux just kept is evaluated and done with, so its popup closes - as
  // its questions fold away in the drawer.
  const decided = useRef<Set<string> | null>(null);
  useEffect(() => {
    const now = new Set(routes.flatMap((r) => r.cruxes.filter(isDecided).map((c) => c.id)));
    const before = decided.current;
    decided.current = now;
    if (!before) return;
    for (const route of routes) {
      for (const crux of route.cruxes) {
        if (now.has(crux.id) && !before.has(crux.id)) {
          markers.current.get(markerKey(route.id, crux.number))?.closePopup();
        }
      }
    }
  }, [routes]);

  const shown = useMemo(
    () =>
      routes
        .filter((route) => route.visible && route.cruxes.length > 0)
        .map((route) => ({
          route,
          cruxes: route.cruxes.flatMap((crux): ShownCrux[] =>
            shelfOf(crux) === "active"
              ? [
                  {
                    ...crux,
                    critical: isCritical(overallOf(crux)),
                    // Placed or moved by the user: marked right where they put
                    // it. Identified: ahead of the area they are walking into.
                    markerPosition:
                      crux.source === "manual" || crux.moved
                        ? crux.position
                        : markerSpot(route.line, crux.position),
                  },
                ]
              : []
          ),
        })),
    [routes]
  );

  // Absolute layer pixels at this zoom: they move when the map zooms, not
  // when it pans, so panning never re-clusters.
  const clustered = useMemo(
    () =>
      shown.map(({ route, cruxes }) => {
        const selected = route.id === selectedId;
        return {
          route,
          selected,
          clusters: clusterCruxes(
            cruxes,
            (crux) => map.project([crux.markerPosition.lat, crux.markerPosition.lng], zoom),
            (crux) => cruxIconSize(crux, selected, `${crux.number}`, verdictOf(crux))
          ),
        };
      }),
    [shown, selectedId, map, zoom]
  );

  // A cluster is opened, not selected: zooming to what it covers is the
  // only thing it can usefully do, and it is what its popup tells you to do.
  const openCluster = useCallback(
    (cluster: CruxCluster<ShownCrux>) => {
      const points = cluster.members.map(
        (crux) => [crux.markerPosition.lat, crux.markerPosition.lng] as [number, number]
      );
      const bounds = latLngBounds(points);
      // Members stacked on one point give an empty bounds, which fitBounds
      // cannot use: step in instead.
      if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
        map.setView(points[0], Math.min(map.getZoom() + 2, map.getMaxZoom()));
      } else {
        map.fitBounds(bounds, { padding: [60, 60] });
      }
    },
    [map]
  );

  useEffect(() => {
    if (focus?.kind !== "crux") return;
    pending.current = focus;
    map.setView([focus.position.lat, focus.position.lng], Math.max(map.getZoom(), 15));
  }, [map, focus]);

  // On the focus itself, so a Crux already at this zoom opens at once, and
  // again whenever the clusters change, so one that needed the zoom to
  // split its cluster opens as soon as it exists. Absent when its Route is
  // hidden: then the map has still gone there.
  useEffect(() => {
    const wanted = pending.current;
    if (wanted?.kind !== "crux") return;
    const marker = markers.current.get(markerKey(wanted.routeId, wanted.number));
    if (marker) {
      marker.openPopup();
      pending.current = null;
    }
  }, [clustered, focus]);

  return (
    <>
      {clustered.flatMap(({ route, selected, clusters }) =>
        clusters.map((cluster) => {
          const grouped = cluster.members.length > 1;
          // Keyed and registered by the Crux it starts at, so focusing any
          // member finds this marker while they are drawn as one.
          const key = markerKey(route.id, cluster.head.number);
          return (
            <Marker
              key={key}
              ref={(marker) => {
                for (const crux of cluster.members) {
                  const memberKey = markerKey(route.id, crux.number);
                  if (marker) markers.current.set(memberKey, marker);
                  else markers.current.delete(memberKey);
                }
              }}
              position={[cluster.head.markerPosition.lat, cluster.head.markerPosition.lng]}
              icon={cruxIcon(
                clusterLabel(cluster),
                cluster.worst,
                selected,
                grouped,
                // A stack carries no verdict of its own: it holds several,
                // and its popup counts them instead.
                grouped ? null : verdictOf(cluster.head)
              )}
              zIndexOffset={selected ? 1000 : 0}
              pane="cruxes"
              eventHandlers={{
                click: () =>
                  grouped ? openCluster(cluster) : onCruxClick(route.id, cluster.head.id),
              }}
            >
              {grouped ? (
                <ClusterPopup cluster={cluster} />
              ) : (
                <CruxPopup crux={cluster.head} />
              )}
            </Marker>
          );
        })
      )}
    </>
  );
};

export default CruxMarkers;
