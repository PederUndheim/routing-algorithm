import { useState } from "react";
import type { FeatureCollection } from "geojson";

import Box from "@mui/material/Box";
import Fab from "@mui/material/Fab";
import Tooltip from "@mui/material/Tooltip";
import Popover from "@mui/material/Popover";
import Typography from "@mui/material/Typography";
import Slider from "@mui/material/Slider";

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
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  return (
    <>
      <Tooltip title="Map settings" placement="left">
        <Fab
          onClick={(e) => setAnchorEl(e.currentTarget)}
          sx={{
            backgroundColor: "#367E98",
            color: "#fff",
            width: 64,
            height: 64,
            boxShadow: "0 8px 20px rgba(0,0,0,0.20)",
            marginBottom: 4,
            transition: "all 0.2s ease",
            "&:hover": {
              backgroundColor: "#367E98",
              transform: "scale(1.05)",
              boxShadow: "0 12px 28px rgba(0,0,0,0.25)",
            },
          }}
        >
          <MapOutlinedIcon sx={{ fontSize: 33 }} />
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
              width: 400,
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
            sx={{ fontWeight: 600, fontSize: 18, color: "white", mb: 1 }}
          >
            Basemaps
          </Typography>
        </Box>

        <Box
          sx={{
            display: "flex",
            gap: 1,
            alignItems: "flex-start",
            justifyContent: "space-between",
            px: 1,
            pb: 1,
            mb: 3,
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
                  width: 150,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                }}
              >
                {/* Circle thumbnail */}
                <Box
                  sx={{
                    width: 80,
                    height: 80,
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
                    fontSize: 14,
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
          sx={{ fontWeight: 600, fontSize: 18, color: "white", mb: 1 }}
        >
          Overlays
        </Typography>

        <Box
          sx={{
            display: "flex",
            gap: 1,
            flexDirection: "column",
            pl: 3,
            mb: 3,
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
                  gap: 2,
                }}
              >
                <Box
                  onClick={() => onToggleOverlay(o.id)}
                  sx={{
                    width: 80,
                    height: 80,
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
                    fontSize: 14,
                    fontWeight: 500,
                    color: "white",
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
                    width: 170,
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
                      "& .MuiSlider-thumb": { width: 14, height: 14 },
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
        />
      </Popover>
    </>
  );
};

export default BasemapControl;
