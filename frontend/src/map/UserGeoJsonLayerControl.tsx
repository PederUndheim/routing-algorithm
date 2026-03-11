import type { UserGeoJsonLayer } from "../types/mapTypes";
import type { FeatureCollection } from "geojson";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import DeleteIcon from "@mui/icons-material/Delete";
import PolylineIcon from "@mui/icons-material/Polyline";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";

type UserGeoJsonLayerControlProps = {
  layers: UserGeoJsonLayer[];
  geoJsonVisible: boolean;
  onToggleGeoJsonVisible: () => void;
  onAdd: (name: string, data: FeatureCollection) => void;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
  thumbSize: number;
  contentInset: number;
  rowGap: number;
};

const readFileAsText = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = reject;
    r.readAsText(file);
  });

const UserGeoJsonLayerControl = ({
  layers,
  geoJsonVisible,
  onToggleGeoJsonVisible,
  onAdd,
  onToggle,
  onRemove,
  thumbSize,
  contentInset,
  rowGap,
}: UserGeoJsonLayerControlProps) => {
  const onPickFile = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    for (const file of Array.from(files))
      try {
        const txt = await readFileAsText(file);
        const json = JSON.parse(txt) as FeatureCollection;
        onAdd(file.name.replace(/\.geojson$/i, ""), json);
      } catch (e) {
        console.error(e);
        alert("Could not read this file as GeoJSON.");
      }
  };
  const hasLayers = layers.length > 0;
  const anySelectedVisible = layers.some((l) => l.visible);
  const effectiveVisible = geoJsonVisible && anySelectedVisible;

  return (
    <Box sx={{ mt: { xs: 1.5, sm: 2 }, width: "100%" }}>
      <Typography sx={{ fontWeight: 600, fontSize: { xs: 16, sm: 18 }, color: "white", mb: 1 }}>
        GeoJSON
      </Typography>

      <Box
        sx={{
          display: "flex",
          flexDirection: { xs: "column", sm: "row" },
          alignItems: { xs: "stretch", sm: "center" },
          gap: { xs: 1, sm: rowGap },
          pl: { xs: 0.5, sm: contentInset },
          pr: { xs: 0.5, sm: contentInset },
        }}
      >
        {/* Global toggle on/off for GeoJSON layers */}
        <Box
          sx={{
            display: "flex",
            flexDirection: { xs: "row", sm: "column" },
            alignItems: "center",
            justifyContent: { xs: "flex-start", sm: "center" },
            gap: { xs: 1.2, sm: 0 },
          }}
        >
          <Box
            sx={{
              width: thumbSize,
              height: thumbSize,
              ml: { xs: 0.5, sm: 0 },
              borderRadius: "50%",
              overflow: "hidden",
              border: "4px solid",
              borderColor: !hasLayers
                ? "rgba(255,255,255,0.18)"
                : effectiveVisible
                ? "#367E98"
                : "rgba(255,255,255,0.18)",
              backgroundColor: effectiveVisible
                ? "rgba(54,126,152,0.18)"
                : "transparent",
              boxShadow: effectiveVisible ? "0 8px 20px rgba(0,0,0,0.2)" : "",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: hasLayers ? "pointer" : "default",
              transition:
                "transform 0.15s ease, background-color 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease",
              "&:hover": hasLayers ? { transform: "scale(1.05)" } : undefined,
            }}
            onClick={() => {
              if (!hasLayers) return;
              onToggleGeoJsonVisible(); // ONLY master toggle
            }}
          >
            <PolylineIcon sx={{ fontSize: thumbSize * 0.55, color: "white" }} />
          </Box>
          <Typography
            sx={{
              mt: { xs: 0, sm: 1 },
              fontSize: { xs: 11, sm: 12 },
              color: "rgba(255,255,255,0.65)",
              whiteSpace: "nowrap",
            }}
          >
            Toggle on/off
          </Typography>
        </Box>

        <Box
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
          sx={{ flex: 1, minWidth: 0 }}
        >
          <Button
            variant="outlined"
            component="label"
            fullWidth
            size="small"
            sx={{
              fontSize: { xs: 10, sm: 13 },
              borderColor: "#367E98",
              color: "white",
              "&:hover": { backgroundColor: "rgba(54,126,152,0.10)" },
            }}
          >
            Add GeoJSON layer(s)
            <input
              hidden
              multiple
              type="file"
              accept=".geojson,application/geo+json,application/json"
              onChange={(e) => {
                onPickFile(e.target.files);
                e.currentTarget.value = "";
              }}
            />
          </Button>

          <Box
            sx={{
              mt: 1,
              display: "flex",
              flexDirection: "column",
              gap: 0.5,
              maxHeight: { xs: "min(34dvh, 180px)", sm: 250 },
              width: "100%",
              overflowY: "auto",
              overflowX: "hidden",
              pr: 1,
              // Chrome / Edge / Safari
              "&::-webkit-scrollbar": {
                width: 10,
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
            {layers.length === 0 && (
              <Typography
                sx={{ fontSize: 12, color: "rgba(255,255,255,0.65)" }}
              >
                No files added yet.
              </Typography>
            )}

            {layers.map((l) => (
              <Box
                key={l.id}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: { xs: 0.6, sm: 1 },
                  px: { xs: 0.8, sm: 1 },
                  py: { xs: 0.45, sm: 0.6 },
                  borderRadius: 1.5,
                  background: l.visible
                    ? "rgba(54,126,152,0.18)"
                    : "rgba(255,255,255,0.06)",
                  cursor: "pointer",
                }}
                onClick={() => onToggle(l.id)}
              >
                {l.visible ? (
                  <VisibilityIcon sx={{ color: "#EE7B04", fontSize: 20 }} />
                ) : (
                  <VisibilityOffIcon
                    sx={{
                      color: "rgba(255,255,255,0.35)",
                      fontSize: 20,
                    }}
                  />
                )}

                <Typography
                  sx={{
                    color: "white",
                    fontSize: { xs: 12, sm: 13 },
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: { xs: "clip", sm: "ellipsis" },
                    whiteSpace: { xs: "normal", sm: "nowrap" },
                    wordBreak: "break-word",
                    lineHeight: 1.2,
                  }}
                >
                  {l.name}
                </Typography>
                <IconButton
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(l.id);
                  }}
                >
                  <DeleteIcon
                    sx={{ color: "rgba(255,255,255,0.75)", fontSize: 18 }}
                  />
                </IconButton>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default UserGeoJsonLayerControl;
