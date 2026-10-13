import { Fragment } from "react";
import { Polyline, Popup, Tooltip } from "react-leaflet";
import type { LatLngTuple } from "leaflet";
import type { LineString } from "geojson";

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";

import { geodesicLength } from "../routes/routeList";
import { pointAtDistance, sliceLine } from "../routes/snap";
import type { RouteSuggestion } from "../routes/suggestions";
import { CRUX_COLORS, SUGGESTION_COLORS } from "../theme";
import { latLngsOf } from "./RouteLines";

type SuggestionLinesProps = {
  /** The line the suggestions are for, to show what each would replace. */
  line: LineString;
  suggestions: readonly RouteSuggestion[];
  /** The one open in the drawer, drawn stronger than the rest and with its
   *  choice on the map. */
  activeId: string | null;
  onSelect: (id: string) => void;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  /** Its popup was closed - by a click on the map, or Escape. */
  onClose: (id: string) => void;
};

/** Take it or leave it, on the suggestion itself: a green tick puts its way
 *  into the line, a cross keeps the line as drawn. The same choice as the
 *  card in the drawer. */
const Choice = ({ onAccept, onReject }: { onAccept: () => void; onReject: () => void }) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
    <IconButton
      size="small"
      aria-label="Use this way"
      title="Use this way"
      onClick={onAccept}
      sx={{
        color: "white",
        backgroundColor: CRUX_COLORS.none,
        "&:hover": { backgroundColor: CRUX_COLORS.none, filter: "brightness(1.1)" },
      }}
    >
      <CheckIcon sx={{ fontSize: 18 }} />
    </IconButton>
    <IconButton
      size="small"
      aria-label="Keep my line"
      title="Keep my line"
      onClick={onReject}
      sx={{
        color: "white",
        backgroundColor: CRUX_COLORS.noData,
        "&:hover": { backgroundColor: CRUX_COLORS.noData, filter: "brightness(1.1)" },
      }}
    >
      <CloseIcon sx={{ fontSize: 18 }} />
    </IconButton>
  </Box>
);

/** The Selected route's suggestions, numbered as the drawer numbers them:
 *  its new way dashed beside the line, and a halo on the stretch it would
 *  replace while it is open. Clicking either opens it, here and in the
 *  drawer. */
const SuggestionLines = ({
  line,
  suggestions,
  activeId,
  onSelect,
  onAccept,
  onReject,
  onClose,
}: SuggestionLinesProps) => (
  <>
    {suggestions.map((s, i) => {
      const active = s.id === activeId;
      const faded = activeId !== null && !active;
      const replaced = sliceLine(line, s.startM, s.endM).map(
        ([lng, lat]) => [lat, lng] as LatLngTuple
      );
      const eventHandlers = { click: () => onSelect(s.id) };
      const label = (
        <Tooltip sticky direction="top">
          Suggestion {i + 1}
        </Tooltip>
      );
      const middle = pointAtDistance(s.line, geodesicLength(s.line.coordinates) / 2);
      // A small one is drawn a touch lighter than the rest.
      const way = active ? 3.5 : s.minor ? 2 : 2.5;
      return (
        <Fragment key={s.id}>
          {replaced.length >= 2 && (
            // Shown only while open; otherwise invisible, but still there to
            // be clicked - a stroke at no opacity takes clicks all the same.
            <Polyline
              positions={replaced}
              pathOptions={{
                color: SUGGESTION_COLORS.replaced,
                weight: active ? 14 : 12,
                opacity: active ? 0.35 : 0,
                lineCap: "round",
              }}
              eventHandlers={eventHandlers}
            >
              {!active && label}
            </Polyline>
          )}
          <Polyline
            positions={latLngsOf(s.line)}
            pathOptions={{
              color: SUGGESTION_COLORS.casing,
              weight: way + 3,
              opacity: faded ? 0.15 : active ? 0.7 : 0.45,
            }}
            eventHandlers={eventHandlers}
          >
            {!active && label}
          </Polyline>
          <Polyline
            positions={latLngsOf(s.line)}
            pathOptions={{
              color: SUGGESTION_COLORS.way,
              weight: way,
              opacity: faded ? 0.35 : active ? 1 : s.minor ? 0.7 : 0.85,
              dashArray: "6 6",
            }}
            eventHandlers={eventHandlers}
          />
          {active && (
            // Popups have a pane of their own, above every marker; inside the
            // suggestions pane it would sit under the Crux markers.
            <Popup
              position={[middle.lat, middle.lng]}
              pane="popupPane"
              className="suggestion-choice"
              closeButton={false}
              autoPan={false}
              eventHandlers={{ remove: () => onClose(s.id) }}
            >
              <Choice onAccept={() => onAccept(s.id)} onReject={() => onReject(s.id)} />
            </Popup>
          )}
        </Fragment>
      );
    })}
  </>
);

export default SuggestionLines;
