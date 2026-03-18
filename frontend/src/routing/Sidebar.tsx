import { useEffect, useRef, useState } from "react";

import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import CloseIcon from "@mui/icons-material/Close";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";

import LogoNTNU from "../assets/logos/ntnu.png";
import LogoNVE from "../assets/logos/nve.jpg";
import LogoVarsom from "../assets/logos/varsom.png";

import RouteControls from "./RouteControls";
import type { LatLng, PickMode } from "../types/mapTypes";
import type { CorridorMode } from "../types/corridor";

type SidebarProps = {
  open: boolean;
  onClose: () => void;
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  corridorMode: CorridorMode;
  onCorridorModeChange: (mode: CorridorMode) => void;
  stopPoints: LatLng[];
  onRequestAddStop: () => void;
  onRequestRepickStop: (index: number) => void;
  onRemoveStop: (index: number) => void;
  onMoveStop: (fromIndex: number, toIndex: number) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onClearStops: () => void;
  onGenerate: (params: {
    lambdaWeight: number;
    smoothThreshold: number;
    avoidLake: boolean;
    avoidGlacier: boolean;
    avoidRiver: boolean;
    trackInfluenceMode: "off" | "forest_only" | "balanced" | "strong";
    corridorMode: "conservative" | "balanced" | "explorative";
    stopPoints: LatLng[];
  }) => void;
  runId: string | null;
  gpxDownloadUrl: string | null;
  geojsonDownloadUrl: string | null;
};

const MIN_W = 280;
const MAX_W = 1100;
const DEFAULT_W = 380;

const Sidebar = ({
  open,
  onClose,
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  showCorridor,
  onShowCorridorChange,
  corridorMode,
  onCorridorModeChange,
  stopPoints,
  onRequestAddStop,
  onRequestRepickStop,
  onRemoveStop,
  onMoveStop,
  onClearStart,
  onClearEnd,
  onClearStops,
  onGenerate,
  runId,
  gpxDownloadUrl,
  geojsonDownloadUrl,
}: SidebarProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isLargeDesktop = useMediaQuery(theme.breakpoints.up("xl"));
  const [width, setWidth] = useState(DEFAULT_W);
  const draggingRef = useRef(false);
  const desktopMaxWidth = Math.min(MAX_W, Math.floor(window.innerWidth * 0.58));
  const effectiveWidth = isMobile
    ? Math.min(window.innerWidth * 0.75, 420)
    : Math.max(MIN_W, Math.min(width, desktopMaxWidth));

  useEffect(() => {
    if (isMobile) return;
    setWidth((prev) => {
      if (prev !== DEFAULT_W) return prev;
      return isLargeDesktop ? 380 : 360;
    });
  }, [isMobile, isLargeDesktop]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const maxForViewport = Math.min(MAX_W, Math.floor(window.innerWidth * 0.58));
      const next = Math.max(MIN_W, Math.min(maxForViewport, e.clientX));
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
      variant={isMobile ? "temporary" : "persistent"}
      onClose={onClose}
      ModalProps={{
        keepMounted: true,
        hideBackdrop: !isMobile,
        disableEnforceFocus: true,
        disableAutoFocus: true,
        disableRestoreFocus: true,
      }}
      sx={{
        width: effectiveWidth,
        flexShrink: 0,
        "& .MuiDrawer-paper": {
          width: effectiveWidth,
          backgroundColor: "#555555",
          overflow: "visible",
          display: "flex",
          flexDirection: "column",
          boxSizing: "border-box",
          borderRight: "1px solid rgba(0,0,0,0.12)",
        },
      }}
    >
      {/* Header */}
      <Box sx={{ p: 2, pb: { xs: 1, sm: 2 }, display: "flex", alignItems: "center"}}>
        <Typography
          variant={isMobile ? "h6" : "h5"}
          sx={{ flex: 1, color: "white", fontWeight: 540 }}
        >
          Route generation
        </Typography>
        <IconButton onClick={onClose}>
          <CloseIcon sx={{ color: "white" }} />
        </IconButton>
      </Box>

      <Divider color="#EE7B04" variant="middle" />

      <Box
        sx={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          "&::-webkit-scrollbar": {
            width: 6,
          },
          "&::-webkit-scrollbar-track": {
            background: "rgba(255,255,255,0.06)",
            borderRadius: 8,
          },
          "&::-webkit-scrollbar-thumb": {
            backgroundColor: "#367E98",
            borderRadius: 4,
          },
          "&::-webkit-scrollbar-thumb:hover": {
            backgroundColor: "#2c657b",
          },
        }}
      >
        <RouteControls
          startPoint={startPoint}
          endPoint={endPoint}
          pickMode={pickMode}
          onPickModeChange={onPickModeChange}
          showCorridor={showCorridor}
          onShowCorridorChange={onShowCorridorChange}
          corridorMode={corridorMode}
          onCorridorModeChange={onCorridorModeChange}
          stopPoints={stopPoints}
          onRequestAddStop={onRequestAddStop}
          onRequestRepickStop={onRequestRepickStop}
          onRemoveStop={onRemoveStop}
          onMoveStop={onMoveStop}
          onClearStart={onClearStart}
          onClearEnd={onClearEnd}
          onGenerate={onGenerate}
          onClearStops={onClearStops}
          runId={runId}
          gpxDownloadUrl={gpxDownloadUrl}
          geojsonDownloadUrl={geojsonDownloadUrl}
        />
        

        {/* Logos */}
        <Box
          sx={{
            px: 2,
            pb: 2,
            pt: 1,
            mt: "auto",
            display: "flex",
            flexDirection: "row",
            justifyContent: "center",
            gap: { xs: 1.6, sm: 2 },
          }}
        >
          <Box
            component="img"
            src={LogoNVE}
            alt="NVE Logo"
            sx={{ height: { xs: 30, sm: 40 }, objectFit: "contain" }}
          />
          <Box
            component="img"
            src={LogoVarsom}
            alt="Varsom Logo"
            sx={{ height: { xs: 30, sm: 40 }, objectFit: "contain" }}
          />
          <Box
            component="img"
            src={LogoNTNU}
            alt="NTNU Logo"
            sx={{ height: { xs: 30, sm: 40 }, objectFit: "contain" }}
          />
        </Box>
      </Box>

    

      {/* Drag handle */}
      {!isMobile && (
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
      )}
    </Drawer>
  );
};

export default Sidebar;
