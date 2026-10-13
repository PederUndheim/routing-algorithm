import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import DirectionsCarIcon from "@mui/icons-material/DirectionsCar";
import DownloadIcon from "@mui/icons-material/Download";
import DrawIcon from "@mui/icons-material/Draw";
import EditIcon from "@mui/icons-material/Edit";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import RouteIcon from "@mui/icons-material/Route";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";

import { downloadRoute } from "../routes/exportRoute";
import { isRoadRoute } from "../routes/routeList";
import type { Route } from "../routes/routeList";
import { COLORS } from "../theme";
import { SectionHeading } from "./CollapseToggle";
import { LIST_HEIGHT, primarySx, scrollbarSx } from "./styles";

const SOURCE = {
  routed: { Icon: RouteIcon, title: "Generated" },
  drawn: { Icon: DrawIcon, title: "Drawn" },
  uploaded: { Icon: UploadFileIcon, title: "Uploaded" },
} as const;

// A routed Route driven along the roads rather than across terrain.
const ROAD = { Icon: DirectionsCarIcon, title: "Generated on roads" } as const;

type RouteRowProps = {
  route: Route;
  selected: boolean;
  onSelect: () => void;
  onToggleVisible: () => void;
  onDelete: () => void;
  onEdit: () => void;
};

/** One Route: eye, where it came from, its name, download, edit, delete.
 *  Clicking anywhere else on the row selects it. */
const RouteRow = ({ route, selected, onSelect, onToggleVisible, onDelete, onEdit }: RouteRowProps) => {
  const { Icon: SourceIcon, title: sourceTitle } = isRoadRoute(route) ? ROAD : SOURCE[route.source];

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
        titleAccess={sourceTitle}
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

      {/* GPX: the line as a track and the cruxes in play as waypoints - what
          GPS watches and phone apps read. */}
      <IconButton
        size="small"
        aria-label={`Download ${route.name} as GPX`}
        title="Download GPX"
        onClick={(e) => {
          e.stopPropagation();
          downloadRoute(route, "gpx");
        }}
        sx={{ p: 0.25 }}
      >
        <DownloadIcon sx={{ color: "rgba(255,255,255,0.65)", fontSize: 18 }} />
      </IconButton>

      {/* Any Route: a routed or uploaded line is opened simplified, to
          points few enough to drag about. */}
      <IconButton
        size="small"
        aria-label={`Edit ${route.name}`}
        onClick={(e) => {
          e.stopPropagation();
          onEdit();
        }}
        sx={{ p: 0.25 }}
      >
        <EditIcon sx={{ color: "rgba(255,255,255,0.65)", fontSize: 18 }} />
      </IconButton>

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
  onEdit: (id: string) => void;
  open: boolean;
  onToggle: () => void;
  /** Over the list - a Route being edited - and shown even while the list
   *  is folded, since its Save is the way out of editing. */
  banner?: ReactNode;
  /** Under the list and folded with it - the Selected route's corridor -
   *  but outside its scroll, so it stays put however long the list is. */
  children?: ReactNode;
};

const RouteListSection = ({
  routes,
  selectedId,
  onSelect,
  onToggleVisible,
  onDelete,
  onEdit,
  open,
  onToggle,
  banner,
  children,
}: RouteListSectionProps) => (
  <Box>
    <SectionHeading title="Routes" open={open} onToggle={onToggle} what="the routes" />

    {banner}

    {open && (
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: 0.5,
          maxHeight: LIST_HEIGHT,
          overflowY: "auto",
          p: "1px",
          ...scrollbarSx,
        }}
      >
        {routes.length === 0 && (
          <Typography sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}>
            No routes yet - add one above.
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
            onEdit={() => onEdit(route.id)}
          />
        ))}
      </Box>
    )}

    {open && children}
  </Box>
);

/** Runs only when pressed - never on selecting or uploading - and on the
 *  Selected route, so it is off while nothing is selected. */
export const IdentifyButton = ({
  disabled,
  identified,
  isIdentifying,
  onIdentify,
  onStartOver,
}: {
  disabled: boolean;
  /** The Selected route has been through the identifier before: pressing
   *  again updates, keeping what has been done with its Cruxes. */
  identified: boolean;
  isIdentifying: boolean;
  onIdentify: () => void;
  onStartOver: () => void;
}) => (
  <>
    <Button
      variant="contained"
      fullWidth
      size="small"
      disabled={disabled || isIdentifying}
      onClick={onIdentify}
      startIcon={isIdentifying ? <CircularProgress size={14} color="inherit" /> : undefined}
      sx={primarySx}
    >
      {isIdentifying
        ? "Identifying cruxes..."
        : identified
          ? "Update cruxes"
          : "Identify cruxes"}
    </Button>
    {/* Quiet: the way to throw the work away should not sit level with
        the way to keep it. */}
    {identified && (
      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
        <Button
          variant="text"
          size="small"
          startIcon={<RestartAltIcon sx={{ fontSize: "16px !important" }} />}
          disabled={disabled || isIdentifying}
          onClick={onStartOver}
          sx={{
            mt: 0.25,
            px: 0.75,
            fontSize: 12,
            textTransform: "none",
            color: "rgba(255,255,255,0.6)",
            "&:hover": { color: "white", backgroundColor: "rgba(54,126,152,0.15)" },
          }}
        >
          Start over
        </Button>
      </Box>
    )}
  </>
);

export default RouteListSection;
