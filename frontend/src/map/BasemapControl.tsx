import { useState } from "react";
import type { FeatureCollection } from "geojson";

import Box from "@mui/material/Box";
import Fab from "@mui/material/Fab";
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import Slider from "@mui/material/Slider";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

import MapOutlinedIcon from "@mui/icons-material/MapOutlined";

import { BASEMAPS } from "../layers/basemaps";
import type { BasemapId } from "../layers/basemaps";
import { OVERLAYS } from "../layers/overlays";
import type { OverlayId } from "../layers/overlays";
import type { UserGeoJsonLayer } from "../types/mapTypes";

import UserGeoJsonLayerControl from "./UserGeoJsonLayerControl";

type BasemapControlProps = {
  basemap: BasemapId;
  onBasemapChange: (id: BasemapId) => void;

  overlays: Record<OverlayId, boolean>;
  onToggleOverlay: (id: OverlayId) => void;

  overlayOpacity: Record<OverlayId, number>;
  onOverlayOpacityChange: (id: OverlayId, opacity: number) => void;
  userGeoJsonLayers: UserGeoJsonLayer[];
  onAddGeoJson: (name: string, data: FeatureCollection) => void;
  onToggleGeoJson: (id: string) => void;
  onRemoveGeoJson: (id: string) => void;
  geoJsonVisible: boolean;
  onToggleGeoJsonVisible: () => void;
};

const BasemapControl = ({
  basemap,
  onBasemapChange,
  overlays,
  onToggleOverlay,
  overlayOpacity,
  onOverlayOpacityChange,
  userGeoJsonLayers,
  onAddGeoJson,
  onToggleGeoJson,
  onRemoveGeoJson,
  geoJsonVisible,
  onToggleGeoJsonVisible,
}: BasemapControlProps) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isLarge = useMediaQuery(theme.breakpoints.up("xl"));
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);
  const fabSize = isMobile ? 55 : isLarge ? 72 : 64;
  const thumbSize = isMobile ? 50 : isLarge ? 92 : 80;
  const controlInset = isMobile ? 1 : isLarge ? 3.5 : 3;
  const controlGap = isMobile ? 1.25 : isLarge ? 2.5 : 2;
  const overlayLabelWidth = isMobile ? 54 : isLarge ? 68 : 60;
  const sliderWidth = isMobile ? 125 : isLarge ? 210 : 180;
  const sliderThumbSize = isMobile ? 12 : isLarge ? 16 : 14;
  const popoverWidth = isMobile ? 277 : isLarge ? 460 : 400;

  return (
    <>
      <Tooltip title="Map settings" placement="left">
        <Fab
          onClick={(e) => setAnchorEl(e.currentTarget)}
          sx={{
            backgroundColor: "#367E98",
            color: "#fff",
            width: fabSize,
            height: fabSize,
            boxShadow: "0 8px 20px rgba(0,0,0,0.20)",
            marginBottom: { xs: 1, sm: 4 },
            transition: "all 0.2s ease",
            "&:hover": {
              backgroundColor: "#367E98",
              transform: "scale(1.05)",
              boxShadow: "0 12px 28px rgba(0,0,0,0.25)",
            },
          }}
        >
          <MapOutlinedIcon sx={{ fontSize: isMobile ? 32 : isLarge ? 38 : 34 }} />
        </Fab>
      </Tooltip>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: "center", horizontal: "left" }}
        transformOrigin={{ vertical: "center", horizontal: "right" }}
        slotProps={{
          paper: {
            sx: {
              backgroundColor: "#555555",
              p: 2,
              borderRadius: 3,
              width: popoverWidth,
              maxWidth: "calc(100vw - 24px)",
              maxHeight: "calc(100dvh - 24px)",
              overflowY: "auto",
              ml: -2,
            },
          },
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          {/* Basemaps row */}
          <Typography
            sx={{ fontWeight: 600, fontSize: { xs: 16, sm: 18 }, color: "white", mb: 1 }}
          >
            Basemaps
          </Typography>
        </Box>

        <Box
          sx={{
            display: "flex",
            gap: 1,
            justifyContent: "center",
            flexWrap: "nowrap",
            overflowX: "auto",
            overflowY: "hidden",
            pb: 1.2,
            pt: 1,
            px: 1,
            mb: { xs: 1, sm: 3 },
            scrollbarWidth: "thin",
            scrollbarColor: "#367E98 rgba(255,255,255,0.08)",
            "&::-webkit-scrollbar": {
              height: 8,
            },
            "&::-webkit-scrollbar-track": {
              background: "rgba(255,255,255,0.08)",
              borderRadius: 8,
            },
            "&::-webkit-scrollbar-thumb": {
              backgroundColor: "#367E98",
              borderRadius: 8,
            },
          }}
        >
          {BASEMAPS.map((b) => {
            const isSelected = b.id === basemap;

            return (
              <Box
                key={b.id}
                onClick={() => onBasemapChange(b.id)}
                sx={{
                  cursor: "pointer",
                  userSelect: "none",
                  textAlign: "center",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                }}
              >
                {/* Circle thumbnail */}
                <Box
                  sx={{
                    width: thumbSize,
                    height: thumbSize,
                    flexShrink: 0,
                    borderRadius: "50%",
                    overflow: "hidden",
                    border: isSelected
                      ? "3px solid #EE7B04"
                      : "3px solid transparent",
                    boxShadow: "0 8px 20px rgba(0,0,0,0.2)",
                    transition:
                      "transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease",
                    "&:hover": {
                      transform: "scale(1.05)",
                    },
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
                      filter: isSelected
                        ? "none"
                        : "saturate(0.95) brightness(0.98)",
                    }}
                  />
                </Box>

                {/* Label under circle */}
                <Typography
                  sx={{
                    mt: 0.5,
                    fontSize: { xs: 12, sm: 14 },
                    fontWeight: isSelected ? 700 : 500,
                    color: "white",
                  }}
                >
                  {b.label}
                </Typography>
              </Box>
            );
          })}
        </Box>

        {/* Overlays row */}
        <Typography
          sx={{ fontWeight: 600, fontSize: { xs: 16, sm: 18 }, color: "white", mb: 1 }}
        >
          Overlays
        </Typography>

        <Box
          sx={{
            display: "flex",
            gap: { xs: 0, sm: 1 },
            flexDirection: "column",
            pl: controlInset,
            pr: controlInset,
            mb: { xs: 0, sm: 3 },
          }}
        >
          {OVERLAYS.map((o) => {
            const enabled = overlays[o.id];
            const opacity = overlayOpacity[o.id] ?? o.opacityDefault;

            return (
              <Box
                key={o.id}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  cursor: "pointer",
                  gap: controlGap,
                  marginBottom: 0.5,
                  pr: controlInset,
                }}
              >
                <Box
                  onClick={() => onToggleOverlay(o.id)}
                  sx={{
                    width: thumbSize,
                    height: thumbSize,
                    flexShrink: 0,
                    borderRadius: "50%",
                    overflow: "hidden",
                    border: enabled
                      ? "4px solid #367E98"
                      : "4px solid transparent",
                    boxShadow: "0 8px 20px rgba(0,0,0,0.2)",
                    transition:
                      "transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease",
                    "&:hover": {
                      transform: "scale(1.05)",
                    },
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
                      filter: enabled
                        ? "none"
                        : "saturate(0.95) brightness(0.98)",
                    }}
                  />
                </Box>

                <Typography
                  sx={{
                    fontSize: { xs: 12, sm: 14 },
                    fontWeight: 500,
                    color: "white",
                    width: overlayLabelWidth,
                  }}
                >
                  {o.label}
                </Typography>

                {/* Slider appears only when enabled */}
                <Box
                  display={"flex"}
                  flexDirection={"column"}
                  alignItems={"center"}
                  sx={{
                    width: sliderWidth,
                    opacity: enabled ? 1 : 0.5,
                    pointerEvents: enabled ? "auto" : "none",
                    transition: "opacity 0.15s ease",
                  }}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  <Slider
                    value={opacity}
                    min={0}
                    max={1}
                    step={0.01}
                    disabled={!enabled}
                    onChange={(_, v) =>
                      onOverlayOpacityChange(o.id, v as number)
                    }
                    valueLabelDisplay="auto"
                    valueLabelFormat={(v) =>
                      `${Math.round((v as number) * 100)}%`
                    }
                    sx={{
                      color: "#367E98",
                      "& .MuiSlider-thumb": {
                        width: sliderThumbSize,
                        height: sliderThumbSize,
                      },
                    }}
                  />

                  <Typography
                    sx={{
                      fontSize: 12,
                      fontWeight: 500,
                      color: "white",
                    }}
                  >
                    {"Opacity [%]"}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
        <UserGeoJsonLayerControl
          layers={userGeoJsonLayers}
          geoJsonVisible={geoJsonVisible}
          onToggleGeoJsonVisible={onToggleGeoJsonVisible}
          onAdd={onAddGeoJson}
          onToggle={onToggleGeoJson}
          onRemove={onRemoveGeoJson}
          thumbSize={thumbSize}
          contentInset={controlInset}
          rowGap={controlGap}
        />
      </Popover>
    </>
  );
};

export default BasemapControl;
