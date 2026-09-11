import { useState } from "react";

import Box from "@mui/material/Box";
import Fab from "@mui/material/Fab";
import Popover from "@mui/material/Popover";
import Slider from "@mui/material/Slider";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

import MapOutlinedIcon from "@mui/icons-material/MapOutlined";

import { BASEMAPS } from "../layers/basemaps";
import type { BasemapId } from "../layers/basemaps";
import { OVERLAYS } from "../layers/overlays";
import type { OverlayId } from "../layers/overlays";
import { COLORS, SHADOW, SHADOW_HOVER } from "../theme";

type LayerControlProps = {
  basemap: BasemapId;
  onBasemapChange: (id: BasemapId) => void;
  overlays: Record<OverlayId, boolean>;
  onToggleOverlay: (id: OverlayId) => void;
  overlayOpacity: Record<OverlayId, number>;
  onOverlayOpacityChange: (id: OverlayId, opacity: number) => void;
};

/** The map-settings popover: which basemap, and which NVE overlay on top of
 *  it. Each layer is a circular thumbnail - the picture says more than the
 *  name does, and it keeps the whole control to one screenful. */
const LayerControl = ({
  basemap,
  onBasemapChange,
  overlays,
  onToggleOverlay,
  overlayOpacity,
  onOverlayOpacityChange,
}: LayerControlProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isLarge = useMediaQuery(theme.breakpoints.up("xl"));
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const fabSize = isMobile ? 55 : isLarge ? 72 : 64;
  const thumbSize = isMobile ? 50 : isLarge ? 92 : 80;
  const popoverWidth = isMobile ? 277 : isLarge ? 460 : 400;
  const sliderWidth = isMobile ? 125 : isLarge ? 210 : 180;
  const labelWidth = isMobile ? 54 : isLarge ? 68 : 60;

  const heading = {
    fontWeight: 600,
    fontSize: { xs: 16, sm: 18 },
    color: "white",
    mb: 1,
  };

  return (
    <>
      <Tooltip title="Map settings" placement="left">
        <Fab
          onClick={(e) => setAnchorEl(e.currentTarget)}
          sx={{
            backgroundColor: COLORS.teal,
            color: "#fff",
            width: fabSize,
            height: fabSize,
            boxShadow: SHADOW,
            marginBottom: { xs: 1, sm: 4 },
            transition: "all 0.2s ease",
            "&:hover": {
              backgroundColor: COLORS.teal,
              transform: "scale(1.05)",
              boxShadow: SHADOW_HOVER,
            },
          }}
        >
          <MapOutlinedIcon sx={{ fontSize: isMobile ? 32 : isLarge ? 38 : 34 }} />
        </Fab>
      </Tooltip>

      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "center", horizontal: "left" }}
        transformOrigin={{ vertical: "center", horizontal: "right" }}
        slotProps={{
          paper: {
            sx: {
              backgroundColor: COLORS.panel,
              p: 2,
              ml: -2,
              borderRadius: 3,
              width: popoverWidth,
              maxWidth: "calc(100vw - 24px)",
              maxHeight: "calc(100dvh - 54px)",
              overflowX: "hidden",
            },
          },
        }}
      >
        <Typography sx={heading}>Basemaps</Typography>

        <Box
          sx={{
            display: "flex",
            gap: 1,
            justifyContent: "center",
            overflowX: "auto",
            pt: 1,
            pb: 1.2,
            px: 1,
            mb: { xs: 1, sm: 3 },
            "&::-webkit-scrollbar": { height: 8 },
            "&::-webkit-scrollbar-track": {
              background: "rgba(255,255,255,0.08)",
              borderRadius: 8,
            },
            "&::-webkit-scrollbar-thumb": {
              backgroundColor: COLORS.teal,
              borderRadius: 8,
            },
          }}
        >
          {BASEMAPS.map((b) => {
            const selected = b.id === basemap;

            return (
              <Box
                key={b.id}
                onClick={() => onBasemapChange(b.id)}
                sx={{
                  cursor: "pointer",
                  userSelect: "none",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                }}
              >
                <Box
                  sx={{
                    width: thumbSize,
                    height: thumbSize,
                    flexShrink: 0,
                    borderRadius: "50%",
                    overflow: "hidden",
                    border: "3px solid " + (selected ? COLORS.orange : "transparent"),
                    boxShadow: SHADOW,
                    transition: "transform 0.15s ease, border-color 0.15s ease",
                    "&:hover": { transform: "scale(1.05)" },
                  }}
                >
                  <Box
                    component="img"
                    src={b.thumbUrl}
                    alt={b.label}
                    sx={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      display: "block",
                    }}
                  />
                </Box>

                <Typography
                  sx={{
                    mt: 0.5,
                    fontSize: { xs: 12, sm: 14 },
                    fontWeight: selected ? 700 : 500,
                    color: "white",
                  }}
                >
                  {b.label}
                </Typography>
              </Box>
            );
          })}
        </Box>

        <Typography sx={heading}>Overlays</Typography>

        <Box sx={{ display: "flex", flexDirection: "column", px: { xs: 1, sm: 3 } }}>
          {OVERLAYS.map((o) => {
            const enabled = overlays[o.id];
            const opacity = overlayOpacity[o.id] ?? o.opacityDefault;

            return (
              <Box
                key={o.id}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: { xs: 1.25, sm: 2 },
                  mb: 0.5,
                }}
              >
                <Box
                  onClick={() => onToggleOverlay(o.id)}
                  sx={{
                    width: thumbSize,
                    height: thumbSize,
                    flexShrink: 0,
                    cursor: "pointer",
                    borderRadius: "50%",
                    overflow: "hidden",
                    border: "4px solid " + (enabled ? COLORS.teal : "transparent"),
                    boxShadow: SHADOW,
                    transition: "transform 0.15s ease, border-color 0.15s ease",
                    "&:hover": { transform: "scale(1.05)" },
                  }}
                >
                  <Box
                    component="img"
                    src={o.thumbUrl}
                    alt={o.label}
                    sx={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      display: "block",
                    }}
                  />
                </Box>

                <Typography
                  sx={{
                    fontSize: { xs: 12, sm: 14 },
                    fontWeight: 500,
                    color: "white",
                    width: labelWidth,
                  }}
                >
                  {o.label}
                </Typography>

                {/* Kept in the layout but dimmed when the layer is off, so the
                    row does not change height as you toggle it. */}
                <Box
                  sx={{
                    width: sliderWidth,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    opacity: enabled ? 1 : 0.5,
                    pointerEvents: enabled ? "auto" : "none",
                    transition: "opacity 0.15s ease",
                  }}
                >
                  <Slider
                    value={opacity}
                    min={0}
                    max={1}
                    step={0.01}
                    disabled={!enabled}
                    onChange={(_, v) => onOverlayOpacityChange(o.id, v as number)}
                    valueLabelDisplay="auto"
                    valueLabelFormat={(v) => Math.round(v * 100) + "%"}
                    sx={{
                      color: COLORS.teal,
                      "& .MuiSlider-thumb": {
                        width: isMobile ? 12 : 14,
                        height: isMobile ? 12 : 14,
                      },
                    }}
                  />
                  <Typography sx={{ fontSize: 12, fontWeight: 500, color: "white" }}>
                    Opacity [%]
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Popover>
    </>
  );
};

export default LayerControl;
