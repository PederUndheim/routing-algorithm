import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import { latLngBounds } from "leaflet";

import type { MapFocus } from "../types";
import { latLngsOf } from "./RouteLines";

type FocusControllerProps = {
  focus: MapFocus | null;
  /** How much of the map's left edge the drawer covers, in pixels. */
  leftInset: number;
};

/** Frames each newly focused Route, keeping it clear of the drawer and the
 *  buttons down the right. Renders nothing. A focus on one Crux is
 *  CruxMarkers' to answer, since it has the popup to open. */
const FocusController = ({ focus, leftInset }: FocusControllerProps) => {
  const map = useMap();

  // Read when focusing, but not a reason to focus again: opening or closing
  // the drawer must not re-frame the map.
  const inset = useRef(leftInset);
  useEffect(() => {
    inset.current = leftInset;
  }, [leftInset]);

  useEffect(() => {
    if (focus?.kind !== "route") return;
    map.fitBounds(latLngBounds(latLngsOf(focus.line)), {
      paddingTopLeft: [inset.current + 40, 40],
      paddingBottomRight: [90, 40],
      maxZoom: 16,
    });
  }, [map, focus]);

  return null;
};

export default FocusController;
