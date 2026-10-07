import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import DrawIcon from "@mui/icons-material/Draw";
import RouteIcon from "@mui/icons-material/Route";
import UndoIcon from "@mui/icons-material/Undo";
import UploadFileIcon from "@mui/icons-material/UploadFile";

import { km } from "../format";
import { geodesicLength } from "../routes/routeList";
import type { AddMode, LatLng, PickMode } from "../types";
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

const pickLabel = (picking: boolean, chosen: boolean, what: string) => {
  if (picking) return "Click on map...";
  return (chosen ? "Re-pick " : "Pick ") + what;
};

type PointRowProps = {
  what: string;
  point: LatLng | null;
  picking: boolean;
  onPick: () => void;
  onClear: () => void;
};

const PointRow = ({ what, point, picking, onPick, onClear }: PointRowProps) => (
  <Box sx={{ mb: 1 }}>
    <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
      <Button
        variant="outlined"
        size="small"
        fullWidth
        onClick={onPick}
        sx={{ ...outlinedSx, flex: 4, fontSize: 13 }}
      >
        {pickLabel(picking, Boolean(point), what)}
      </Button>

      <Button
        variant="outlined"
        size="small"
        disabled={!point}
        onClick={onClear}
        sx={{
          ...outlinedSx,
          flex: 1,
          borderColor: "rgba(255,255,255,0.35)",
          fontSize: 13,
        }}
      >
        Clear
      </Button>
    </Box>

    {/* Fixed height either way, so the panel does not jump as points land. */}
    <Typography
      sx={{
        mt: 0.5,
        minHeight: 18,
        fontSize: 12,
        color: point ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.4)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      {point ? formatCoord(point) : "Not set"}
    </Typography>
  </Box>
);

type GeneratePaneProps = {
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onGenerate: () => void;
  isRouting: boolean;
  backendReady: boolean | null;
};

export const GeneratePane = ({
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  onClearStart,
  onClearEnd,
  onGenerate,
  isRouting,
  backendReady,
}: GeneratePaneProps) => {
  const canRoute = Boolean(startPoint) && Boolean(endPoint) && !pickMode && !isRouting;

  return (
    <>
      <Typography sx={{ ...hintSx, mb: 1.5 }}>
        Pick start and end points on the map. Adjust the markers afterwards if needed. Click "Generate route" to retrieve least-cost route. The corridor is shown with the "show corridor".
      </Typography>

      <PointRow
        what="start point"
        point={startPoint}
        picking={pickMode === "start"}
        onPick={() => onPickModeChange("start")}
        onClear={onClearStart}
      />

      <PointRow
        what="end point"
        point={endPoint}
        picking={pickMode === "end"}
        onPick={() => onPickModeChange("end")}
        onClear={onClearEnd}
      />

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
        {isRouting ? "Routing..." : "Generate route"}
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
  /** The drawn Route being edited, or null while drawing a new one. */
  editingName: string | null;
  onUndo: () => void;
  onClear: () => void;
  onFinish: () => void;
  onCancel: () => void;
};

export const DrawPane = ({
  isDrawing,
  onStart,
  points,
  editingName,
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
      {editingName && (
        <Typography sx={{ color: "white", fontSize: 13, fontWeight: 600, mb: 0.5 }}>
          Editing {editingName}
        </Typography>
      )}

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
          {editingName ? "Save changes" : "Add route"}
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
