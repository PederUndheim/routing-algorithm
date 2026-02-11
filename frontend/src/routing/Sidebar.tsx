import { useEffect, useRef, useState } from "react";

import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Chip from "@mui/material/Chip";
import CloseIcon from "@mui/icons-material/Close";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";

import LogoNTNU from "../assets/logos/ntnu.png";
import LogoNVE from "../assets/logos/nve.jpg";
import LogoVarsom from "../assets/logos/varsom.png";

import RouteControls from "./RouteControls";
import type { LatLng, PickMode } from "../types/mapTypes";

type SidebarProps = {
  open: boolean;
  onClose: () => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onGenerate: (params: {
    lambdaWeight: number;
    smoothThreshold: number;
  }) => void;
};

const MIN_W = 250;
const MAX_W = 800;
const DEFAULT_W = 330;

const Sidebar = ({
  open,
  onClose,
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  onClearStart,
  onClearEnd,
  onGenerate,
}: SidebarProps) => {
  const [width, setWidth] = useState(DEFAULT_W);
  const draggingRef = useRef(false);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const next = Math.max(MIN_W, Math.min(MAX_W, e.clientX));
      setWidth(next);
    };
    const onUp = () => {
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  return (
    <Drawer
      anchor="left"
      open={open}
      variant="persistent"
      onClose={onClose}
      ModalProps={{
        keepMounted: true,
        hideBackdrop: true,
        disableEnforceFocus: true,
        disableAutoFocus: true,
        disableRestoreFocus: true,
      }}
      sx={{
        width: width,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width: width,
          backgroundColor: "#555555",
          overflow: "visible",
          boxSizing: "border-box",
          borderRight: "1px solid rgba(0,0,0,0.12)",
        },
      }}
    >
      {/* Header */}
      <Box sx={{ p: 2, display: "flex", alignItems: "center", gap: 1 }}>
        <Typography
          variant="h5"
          sx={{ flex: 1, color: "white", fontWeight: 540 }}
        >
          Route generation
        </Typography>
        <IconButton onClick={onClose}>
          <CloseIcon sx={{ color: "white" }} />
        </IconButton>
      </Box>

      <Divider color="#EE7B04" variant="middle" />

      <RouteControls
        startPoint={startPoint}
        endPoint={endPoint}
        pickMode={pickMode}
        onPickModeChange={onPickModeChange}
        onClearStart={onClearStart}
        onClearEnd={onClearEnd}
        onGenerate={onGenerate}
      />

      {/* Logos */}
      <Box
        sx={{
          position: "absolute",
          bottom: 16,
          left: 16,
          right: 16,
          display: "flex",
          flexDirection: "row",
          justifyContent: "center",
          gap: 2,
        }}
      >
        <Box
          component="img"
          src={LogoNVE}
          alt="NVE Logo"
          sx={{ height: 40, objectFit: "contain" }}
        />
        <Box
          component="img"
          src={LogoVarsom}
          alt="Varsom Logo"
          sx={{ height: 40, objectFit: "contain" }}
        />
        <Box
          component="img"
          src={LogoNTNU}
          alt="NTNU Logo"
          sx={{ height: 40, objectFit: "contain" }}
        />
      </Box>

      {/* Drag handle */}
      <Box
        onMouseDown={() => {
          draggingRef.current = true;
          document.body.style.cursor = "col-resize";
          document.body.style.userSelect = "none";
        }}
        sx={{
          position: "absolute",
          top: 0,
          right: -4,
          width: 10,
          height: "100%",
          cursor: "col-resize",
          zIndex: 1400,
          "&:hover": {
            backgroundColor: "rgba(0,0,0,0.16)",
          },
        }}
      >
        <IconButton
          onClick={onClose}
          size="small"
          sx={{
            borderRadius: 2,
            width: 20,
            height: 40,
            position: "absolute",
            top: "50%",
            right: -6,
            transform: "translateY(-50%)",
            backgroundColor: "#555555",
            zIndex: 1500,
            "&:hover": {
              backgroundColor: "#777777",
              boxShadow: "0 0 5px rgba(0,0,0,0.3)",
            },
          }}
        >
          <ChevronLeftIcon sx={{ color: "white", fontSize: 30 }} />
        </IconButton>
      </Box>
    </Drawer>
  );
};

export default Sidebar;
