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
 *  a halo on the stretch each would replace, and its new way dashed beside
 *  it. Clicking either opens it, here and in the drawer. */
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
      return (
        <Fragment key={s.id}>
          {replaced.length >= 2 && (
            <Polyline
              positions={replaced}
              pathOptions={{
                color: SUGGESTION_COLORS.replaced,
                weight: active ? 16 : 12,
                opacity: faded ? 0.12 : active ? 0.45 : 0.28,
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
              weight: active ? 8 : 6,
              opacity: faded ? 0.25 : 0.75,
            }}
            eventHandlers={eventHandlers}
          >
            {!active && label}
          </Polyline>
          <Polyline
            positions={latLngsOf(s.line)}
            pathOptions={{
              color: SUGGESTION_COLORS.way,
              weight: active ? 4 : 3,
              opacity: faded ? 0.4 : 1,
              dashArray: "7 7",
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
