import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Switch from "@mui/material/Switch";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import AddLocationAltIcon from "@mui/icons-material/AddLocationAlt";
import AdsClickIcon from "@mui/icons-material/AdsClick";
import CloseIcon from "@mui/icons-material/Close";
import DirectionsCarIcon from "@mui/icons-material/DirectionsCar";
import DrawIcon from "@mui/icons-material/Draw";
import EditLocationAltIcon from "@mui/icons-material/EditLocationAlt";
import RouteIcon from "@mui/icons-material/Route";
import UndoIcon from "@mui/icons-material/Undo";
import UploadFileIcon from "@mui/icons-material/UploadFile";

import { km } from "../format";
import { geodesicLength } from "../routes/routeList";
import { allRoad, pointLabel } from "../routes/waypoints";
import type { AddMode, LatLng, PickMode, RouteNetwork, Waypoints } from "../types";
import { COLORS } from "../theme";
import { accentOutlinedSx, hintSx, outlinedSx } from "./styles";

const MODES: { mode: AddMode; label: string; Icon: typeof RouteIcon }[] = [
  { mode: "generate", label: "Generate", Icon: RouteIcon },
  { mode: "draw", label: "Draw", Icon: DrawIcon },
  { mode: "upload", label: "Upload", Icon: UploadFileIcon },
];

/** Three ways to add a Route, side by side, exactly one chosen. */
export const ModePicker = ({
  mode,
  onChange,
}: {
  mode: AddMode;
  onChange: (mode: AddMode) => void;
}) => (
  <ToggleButtonGroup
    exclusive
    fullWidth
    size="small"
    value={mode}
    // Pressing the chosen one again would deselect it; one is always chosen.
    onChange={(_, next: AddMode | null) => {
      if (next) onChange(next);
    }}
    sx={{
      "& .MuiToggleButton-root": {
        gap: 0.75,
        fontSize: 13,
        color: "rgba(255,255,255,0.75)",
        borderColor: "rgba(255,255,255,0.25)",
        "&:hover": { backgroundColor: "rgba(54,126,152,0.15)" },
      },
      "& .MuiToggleButton-root.Mui-selected": {
        color: "white",
        backgroundColor: COLORS.teal,
        borderColor: COLORS.teal,
        "&:hover": { backgroundColor: COLORS.teal },
      },
    }}
  >
    {MODES.map(({ mode: m, label, Icon }) => (
      <ToggleButton key={m} value={m}>
        <Icon sx={{ fontSize: 18 }} />
        {label}
      </ToggleButton>
    ))}
  </ToggleButtonGroup>
);

const formatCoord = (p: LatLng) => p.lat.toFixed(4) + "°N, " + p.lng.toFixed(4) + "°E";

const sameMode = (a: PickMode, b: PickMode) =>
  a !== null &&
  b !== null &&
  a.kind === b.kind &&
  (a.kind === "sequence" || (b.kind !== "sequence" && a.index === b.index));

/** One row of the list: a point, or the one being picked. */
type Slot = { point: LatLng | null; picking: boolean };

/** The points as the list shows them: Start and End even before they are
 *  set, and the point being picked in its place among the rest. */
const slots = (points: readonly LatLng[], mode: PickMode): Slot[] => {
  const shown: Slot[] = points.map((point, i) => ({
    point,
    picking: mode?.kind === "replace" && mode.index === i,
  }));
  if (mode?.kind === "insert") shown.splice(mode.index, 0, { point: null, picking: true });
  if (mode?.kind === "sequence") shown.push({ point: null, picking: true });
  while (shown.length < 2) shown.push({ point: null, picking: false });
  return shown;
};

/** Down the left of the list: a dot for each point, joined by a line for
 *  each leg, so the list reads as the route it is. */
const RAIL_WIDTH = 22;

/** Add waypoint, both ways it reads, so the Drive switch after it lines up
 *  leg to leg. */
const ADD_WIDTH = 124;

const PointDot = ({ index, count }: { index: number; count: number }) => {
  const end = index === count - 1;
  const waypoint = index > 0 && !end;
  return (
    <Box sx={{ width: RAIL_WIDTH, display: "flex", justifyContent: "center", flexShrink: 0 }}>
      <Box
        sx={{
          width: waypoint ? 18 : 12,
          height: waypoint ? 18 : 12,
          boxSizing: "border-box",
          borderRadius: "50%",
          background: end ? COLORS.orange : COLORS.teal,
          border: waypoint ? "1.5px solid white" : "none",
          color: "white",
          fontSize: 10,
          fontWeight: 700,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {waypoint ? index : null}
      </Box>
    </Box>
  );
};

const iconButtonSx = {
  color: "rgba(255,255,255,0.75)",
  "&:hover": { color: "white", backgroundColor: "rgba(54,126,152,0.2)" },
  "&.Mui-disabled": { color: "rgba(255,255,255,0.25)" },
};

/** An icon button whose map click is pending: filled, so it reads as on. */
const activeIconSx = {
  color: "white",
  backgroundColor: COLORS.teal,
  "&:hover": { backgroundColor: COLORS.teal },
};

/** A text button whose map click is pending. */
const activeButtonSx = { backgroundColor: "rgba(54,126,152,0.25)" };

type PointRowProps = {
  index: number;
  count: number;
  slot: Slot;
  /** Absent for a row with nothing to move or remove yet. */
  onRepick?: () => void;
  onRemove?: () => void;
  disabled: boolean;
};

const PointRow = ({ index, count, slot, onRepick, onRemove, disabled }: PointRowProps) => {
  const label = pointLabel(index, count);
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minHeight: 28 }}>
      <PointDot index={index} count={count} />
      <Typography sx={{ color: "white", fontSize: 13, fontWeight: 600, width: 82, flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography
        sx={{
          flex: 1,
          minWidth: 0,
          fontSize: 11,
          color: slot.picking
            ? COLORS.orange
            : slot.point
              ? "rgba(255,255,255,0.5)"
              : "rgba(255,255,255,0.35)",
          fontVariantNumeric: "tabular-nums",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {slot.picking ? "Click on map..." : slot.point ? formatCoord(slot.point) : "Not set"}
      </Typography>
      {onRepick && (
        <IconButton
          size="small"
          aria-label={`Pick the ${label.toLowerCase()} again`}
          title={slot.picking ? "Cancel" : "Pick again on the map"}
          disabled={disabled}
          onClick={onRepick}
          sx={{ ...iconButtonSx, ...(slot.picking ? activeIconSx : {}) }}
        >
          <EditLocationAltIcon sx={{ fontSize: 18 }} />
        </IconButton>
      )}
      {onRemove && (
        <IconButton
          size="small"
          aria-label={`Remove the ${label.toLowerCase()}`}
          title="Remove"
          disabled={disabled}
          onClick={onRemove}
          sx={iconButtonSx}
        >
          <CloseIcon sx={{ fontSize: 18 }} />
        </IconButton>
      )}
    </Box>
  );
};

type LegRowProps = {
  network: RouteNetwork;
  onChange: (network: RouteNetwork) => void;
  inserting: boolean;
  onInsert: () => void;
  disabled: boolean;
};

/** A leg between two points: how it goes, and a way to put a waypoint in
 *  the middle of it. */
const LegRow = ({ network, onChange, inserting, onInsert, disabled }: LegRowProps) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, minHeight: 26 }}>
    <Box
      sx={{
        width: RAIL_WIDTH,
        alignSelf: "stretch",
        display: "flex",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      {/* Dashed for a drive, like a road on a map; solid on foot. */}
      <Box
        sx={{ borderLeft: `2px ${network === "road" ? "dashed" : "solid"} rgba(255,255,255,0.45)` }}
      />
    </Box>
    <AddWaypointLink
      active={inserting}
      onClick={onInsert}
      disabled={disabled}
      title="Add a waypoint on this leg"
    />
    {/* One switch, for driving: off - the default - is over the terrain. */}
    <FormControlLabel
      control={
        <Switch
          size="small"
          checked={network === "road"}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked ? "road" : "terrain")}
          sx={{
            "& .MuiSwitch-switchBase.Mui-checked": { color: COLORS.teal },
            "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
              backgroundColor: COLORS.teal,
            },
          }}
        />
      }
      label={
        <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
          <DirectionsCarIcon sx={{ fontSize: 16 }} />
          Drive
        </Box>
      }
      sx={{
        ml: 0,
        mr: 0,
        color: network === "road" ? "white" : "rgba(255,255,255,0.6)",
        "& .MuiFormControlLabel-label": { fontSize: 12 },
        "& .MuiFormControlLabel-label.Mui-disabled": { color: "rgba(255,255,255,0.4)" },
      }}
    />
  </Box>
);

/** Add waypoint, quiet: grey text and icon, no border - not something every
 *  route needs. Orange while it waits for its map click; pressed again, it
 *  gives up. */
const AddWaypointLink = ({
  active,
  onClick,
  disabled,
  title,
}: {
  active: boolean;
  onClick: () => void;
  disabled: boolean;
  title: string;
}) => (
  <Button
    variant="text"
    size="small"
    title={active ? "Cancel" : title}
    startIcon={<AddLocationAltIcon sx={{ fontSize: "18px !important" }} />}
    disabled={disabled}
    onClick={onClick}
    sx={{
      width: ADD_WIDTH,
      flexShrink: 0,
      justifyContent: "flex-start",
      px: 0.75,
      py: 0.25,
      fontSize: 12,
      textTransform: "none",
      whiteSpace: "nowrap",
      color: active ? COLORS.orange : "rgba(255,255,255,0.65)",
      "&:hover": { color: "white", backgroundColor: "rgba(54,126,152,0.15)" },
      "&.Mui-disabled": { color: "rgba(255,255,255,0.3)" },
    }}
  >
    {active ? "Click on map..." : "Add waypoint"}
  </Button>
);

type GeneratePaneProps = {
  waypoints: Waypoints;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  /** Pick points: the points so far go, and the next two clicks are the
   *  start and the end. */
  onPickPoints: () => void;
  onRemovePoint: (index: number) => void;
  onNetworkChange: (leg: number, network: RouteNetwork) => void;
  onClear: () => void;
  onGenerate: () => void;
  isRouting: boolean;
  backendReady: boolean | null;
};

/** Generate: the points to route through, in order, each leg between two
 *  of them over the terrain or along the roads. */
export const GeneratePane = ({
  waypoints,
  pickMode,
  onPickModeChange,
  onPickPoints,
  onRemovePoint,
  onNetworkChange,
  onClear,
  onGenerate,
  isRouting,
  backendReady,
}: GeneratePaneProps) => {
  const { points, networks } = waypoints;
  const canRoute = points.length >= 2 && !pickMode && !isRouting;
  const shown = slots(points, pickMode);
  const sequencing = pickMode?.kind === "sequence";
  const appending: PickMode = { kind: "insert", index: points.length };
  const isAppending = sameMode(pickMode, appending);
  // Pressing what is already picking stops it.
  const toggle = (mode: PickMode) => onPickModeChange(sameMode(pickMode, mode) ? null : mode);

  // Each row's index among the points, or null for the one being picked -
  // the rows around it are still the points they were.
  let next = 0;
  const pointIndex = shown.map((slot) => (slot.point ? next++ : null));

  return (
    <>
      <Typography sx={{ ...hintSx, mb: 1.5 }}>
        Pick points, then click the start and the end on the map.
      </Typography>

      <Box sx={{ display: "flex", gap: 1, mb: 1 }}>
        <Button
          variant="outlined"
          size="small"
          startIcon={<AdsClickIcon />}
          disabled={isRouting}
          onClick={() => (sequencing ? onPickModeChange(null) : onPickPoints())}
          sx={{ ...outlinedSx, flex: 3, fontSize: 13, ...(sequencing ? activeButtonSx : {}) }}
        >
          {sequencing
            ? points.length === 0
              ? "Click the start..."
              : "Click the end..."
            : "Pick points"}
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={points.length === 0 || isRouting}
          onClick={onClear}
          sx={{ ...outlinedSx, flex: 1, borderColor: "rgba(255,255,255,0.35)", fontSize: 13 }}
        >
          Clear
        </Button>
      </Box>

      <Box sx={{ mb: 0.25 }}>
        {shown.map((slot, row) => {
          const index = pointIndex[row];
          // A leg only between two points that are both there.
          const leg = index !== null && shown[row + 1]?.point ? index : null;
          return (
            <Box key={row}>
              <PointRow
                index={row}
                count={shown.length}
                slot={slot}
                disabled={isRouting}
                onRepick={index !== null ? () => toggle({ kind: "replace", index }) : undefined}
                onRemove={
                  index !== null && !slot.picking ? () => onRemovePoint(index) : undefined
                }
              />
              {leg !== null && (
                <LegRow
                  network={networks[leg]}
                  onChange={(network) => onNetworkChange(leg, network)}
                  inserting={sameMode(pickMode, { kind: "insert", index: leg + 1 })}
                  onInsert={() => toggle({ kind: "insert", index: leg + 1 })}
                  disabled={isRouting}
                />
              )}
            </Box>
          );
        })}
      </Box>

      {/* Under the End, lined up with the legs' own Add waypoint. */}
      <Box sx={{ display: "flex", gap: 0.75, mb: 1.5 }}>
        <Box sx={{ width: RAIL_WIDTH, flexShrink: 0 }} />
        <AddWaypointLink
          active={isAppending}
          onClick={() => toggle(appending)}
          disabled={points.length < 2 || sequencing || isRouting}
          title="Add a waypoint after the end"
        />
      </Box>

      {networks.includes("road") && (
        <Typography sx={{ ...hintSx, mb: 1.5 }}>
          A driven leg snaps to the nearest road and has no corridor.
        </Typography>
      )}

      {backendReady === false && (
        <Typography sx={{ fontSize: 12, color: COLORS.orange, mb: 1.5 }}>
          Backend not reachable on localhost:8000. Start it with
          {" python-qgis.bat -m app.backend.server"}, then reload.
        </Typography>
      )}

      <Button
        variant="outlined"
        fullWidth
        size="small"
        disabled={!canRoute}
        onClick={onGenerate}
        sx={accentOutlinedSx}
      >
        {isRouting ? "Routing..." : allRoad(waypoints) ? "Generate drive" : "Generate route"}
      </Button>
    </>
  );
};

type DrawPaneProps = {
  /** Whether map clicks are adding points yet. Off until asked for, so a
   *  click on the map in Draw mode is still just a click on the map. */
  isDrawing: boolean;
  onStart: () => void;
  points: readonly LatLng[];
  onUndo: () => void;
  onClear: () => void;
  onFinish: () => void;
  onCancel: () => void;
};

export const DrawPane = ({
  isDrawing,
  onStart,
  points,
  onUndo,
  onClear,
  onFinish,
  onCancel,
}: DrawPaneProps) => {
  const lengthM = geodesicLength(points.map((p) => [p.lng, p.lat]));

  if (!isDrawing) {
    return (
      <>
        <Typography sx={{ ...hintSx, mb: 1.5 }}>
          Draw a route: press Start drawing, then click the map to add
          points from start to end.
        </Typography>

        <Button
          variant="outlined"
          fullWidth
          size="small"
          startIcon={<DrawIcon />}
          onClick={onStart}
          sx={accentOutlinedSx}
        >
          Start drawing
        </Button>
      </>
    );
  }

  return (
    <>
      <Typography sx={{ ...hintSx, mb: 1.5 }}>
        Click the map to add points, from start to end. Drag a
        point to move it, drag a small midpoint to bend the line, click a point
        to remove it. When finished, click "Add route" to save it.
      </Typography>

      <Box sx={{ display: "flex", gap: 1, alignItems: "center", mb: 1 }}>
        <Typography
          sx={{
            flex: 1,
            fontSize: 12,
            color: "rgba(255,255,255,0.75)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {points.length} {points.length === 1 ? "point" : "points"}
          {points.length > 1 && ` · ${km(lengthM)}`}
        </Typography>

        <Button
          variant="outlined"
          size="small"
          disabled={points.length === 0}
          onClick={onUndo}
          startIcon={<UndoIcon />}
          sx={{ ...outlinedSx, fontSize: 13 }}
        >
          Undo
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={points.length === 0}
          onClick={onClear}
          sx={{ ...outlinedSx, borderColor: "rgba(255,255,255,0.35)", fontSize: 13 }}
        >
          Clear
        </Button>
      </Box>

      <Box sx={{ display: "flex", gap: 1 }}>
        <Button
          variant="outlined"
          size="small"
          onClick={onCancel}
          sx={{ ...outlinedSx, flex: 1, fontSize: 13 }}
        >
          Cancel
        </Button>
        <Button
          variant="outlined"
          size="small"
          disabled={points.length < 2}
          onClick={onFinish}
          sx={{ ...accentOutlinedSx, flex: 2 }}
        >
          Add route
        </Button>
      </Box>
    </>
  );
};

export const UploadPane = ({ onUpload }: { onUpload: (files: File[]) => void }) => (
  <>
    <Typography sx={{ ...hintSx, mb: 1.5 }}>
      Click the button to upload GPX or GeoJSON file(s). You can also drop the file(s) anywhere on the map.
    </Typography>

    <Button
      variant="outlined"
      component="label"
      fullWidth
      size="small"
      startIcon={<UploadFileIcon />}
      sx={accentOutlinedSx}
    >
      Upload GPX/GeoJSON
      <input
        hidden
        multiple
        type="file"
        accept=".gpx,.geojson,.json,application/gpx+xml,application/geo+json,application/json"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          // Cleared so picking the same file again still fires a change.
          e.currentTarget.value = "";
          if (files.length > 0) onUpload(files);
        }}
      />
    </Button>
  </>
);
