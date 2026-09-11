import type { ReactNode } from "react";

import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

import MyLocationIcon from "@mui/icons-material/MyLocation";
import AddIcon from "@mui/icons-material/Add";
import RemoveIcon from "@mui/icons-material/Remove";

import { COLORS, SHADOW, SHADOW_HOVER } from "../theme";

type ActionButtonProps = {
  title: string;
  onClick: () => void;
  children: ReactNode;
  size: number;
  iconSize: number;
  extraSpace?: boolean;
};

const ActionButton = ({
  title,
  onClick,
  children,
  size,
  iconSize,
  extraSpace,
}: ActionButtonProps) => (
  <Tooltip title={title} placement="left">
    <IconButton
      onClick={onClick}
      sx={{
        marginBottom: extraSpace ? { xs: 2, sm: 4 } : 1,
        borderRadius: 8,
        backgroundColor: COLORS.panel,
        color: "white",
        width: size,
        height: size,
        boxShadow: SHADOW,
        transition: "all 0.2s ease",
        "&:hover": {
          backgroundColor: COLORS.panel,
          transform: "scale(1.03)",
          boxShadow: SHADOW_HOVER,
        },
      }}
    >
      <Box sx={{ fontSize: iconSize, display: "flex", alignItems: "center" }}>
        {children}
      </Box>
    </IconButton>
  </Tooltip>
);

type MapActionsProps = {
  onLocate: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
};

const MapActions = ({ onLocate, onZoomIn, onZoomOut }: MapActionsProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isLarge = useMediaQuery(theme.breakpoints.up("xl"));
  const size = isMobile ? 42 : isLarge ? 56 : 48;
  const iconSize = isMobile ? 22 : isLarge ? 30 : 26;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <ActionButton title="Your position" onClick={onLocate} size={size} iconSize={iconSize} extraSpace>
        <MyLocationIcon />
      </ActionButton>
      <ActionButton title="Zoom in" onClick={onZoomIn} size={size} iconSize={iconSize}>
        <AddIcon />
      </ActionButton>
      <ActionButton title="Zoom out" onClick={onZoomOut} size={size} iconSize={iconSize}>
        <RemoveIcon />
      </ActionButton>
    </Box>
  );
};

export default MapActions;
