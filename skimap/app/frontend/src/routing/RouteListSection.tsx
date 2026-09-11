import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import RouteIcon from "@mui/icons-material/Route";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";

import type { Route } from "../routes/routeList";
import { COLORS } from "../theme";
import { outlinedSx } from "./styles";

type RouteRowProps = {
  route: Route;
  selected: boolean;
  onSelect: () => void;
  onToggleVisible: () => void;
  onDelete: () => void;
};

/** One Route: eye, where it came from, its name, delete. Clicking anywhere
 *  else on the row selects it. */
const RouteRow = ({ route, selected, onSelect, onToggleVisible, onDelete }: RouteRowProps) => {
  const SourceIcon = route.source === "routed" ? RouteIcon : UploadFileIcon;

  return (
    <Box
      onClick={onSelect}
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 0.75,
        pl: 0.25,
        pr: 0.5,
        py: 0.25,
        borderRadius: 1.5,
        cursor: "pointer",
        background: selected ? "rgba(54,126,152,0.35)" : "rgba(255,255,255,0.06)",
        outline: selected ? `1px solid ${COLORS.teal}` : "none",
      }}
    >
      <IconButton
        size="small"
        aria-label={route.visible ? `Hide ${route.name}` : `Show ${route.name}`}
        onClick={(e) => {
          e.stopPropagation();
          onToggleVisible();
        }}
      >
        {route.visible ? (
          <VisibilityIcon sx={{ color: COLORS.orange, fontSize: 20 }} />
        ) : (
          <VisibilityOffIcon sx={{ color: "rgba(255,255,255,0.35)", fontSize: 20 }} />
        )}
      </IconButton>

      <SourceIcon
        titleAccess={route.source === "routed" ? "Routed" : "Uploaded"}
        sx={{ color: "rgba(255,255,255,0.65)", fontSize: 18 }}
      />

      <Typography
        sx={{
          color: "white",
          fontSize: 13,
          flex: 1,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          opacity: route.visible ? 1 : 0.6,
        }}
      >
        {route.name}
      </Typography>

      <IconButton
        size="small"
        aria-label={`Delete ${route.name}`}
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        <DeleteIcon sx={{ color: "rgba(255,255,255,0.75)", fontSize: 18 }} />
      </IconButton>
    </Box>
  );
};

type RouteListSectionProps = {
  routes: readonly Route[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onToggleVisible: (id: string) => void;
  onDelete: (id: string) => void;
  onUpload: (files: File[]) => void;
  isIdentifying: boolean;
  onIdentify: () => void;
};

const RouteListSection = ({
  routes,
  selectedId,
  onSelect,
  onToggleVisible,
  onDelete,
  onUpload,
  isIdentifying,
  onIdentify,
}: RouteListSectionProps) => (
  <Box>
    <Typography sx={{ color: "white", fontWeight: 600, fontSize: 16, mb: 1 }}>
      Routes
    </Typography>

    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 0.5,
        maxHeight: 250,
        overflowY: "auto",
        p: "1px",
      }}
    >
      {routes.length === 0 && (
        <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
          No routes yet. Generate one above, or upload a GPX or GeoJSON - or
          drop the files on the map.
        </Typography>
      )}

      {routes.map((route) => (
        <RouteRow
          key={route.id}
          route={route}
          selected={route.id === selectedId}
          onSelect={() => onSelect(route.id)}
          onToggleVisible={() => onToggleVisible(route.id)}
          onDelete={() => onDelete(route.id)}
        />
      ))}
    </Box>

    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mt: 1 }}>
      <Button
        variant="outlined"
        component="label"
        size="small"
        startIcon={<UploadFileIcon />}
        sx={{ ...outlinedSx, fontSize: 13 }}
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

      {/* Runs only when pressed - never on selecting or uploading - and on
          the Selected route, so it is off while nothing is selected. */}
      <Button
        variant="outlined"
        size="small"
        disabled={selectedId === null || isIdentifying}
        onClick={onIdentify}
        startIcon={isIdentifying ? <CircularProgress size={14} color="inherit" /> : undefined}
        sx={{ ...outlinedSx, borderColor: COLORS.orange, fontSize: 13 }}
      >
        {isIdentifying ? "Identifying cruxes..." : "Identify cruxes"}
      </Button>
    </Box>
  </Box>
);

export default RouteListSection;
