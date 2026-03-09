import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Slider from "@mui/material/Slider";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Stack from "@mui/material/Stack";
import FileDownloadIcon from "@mui/icons-material/FileDownload";

import { useEffect, useState } from "react";

import type { LatLng, PickMode } from "../types/mapTypes";

type RouteControlsProps = {
  startPoint: LatLng | null;
  endPoint: LatLng | null;
  pickMode: PickMode;
  onPickModeChange: (mode: PickMode) => void;
  showCorridor: boolean;
  onShowCorridorChange: (show: boolean) => void;
  onClearStart: () => void;
  onClearEnd: () => void;
  onGenerate: (params: {
    lambdaWeight: number;
    smoothThreshold: number;
  }) => void;
  runId: string | null;
  gpxDownloadUrl: string | null;
  geojsonDownloadUrl: string | null;
};

const formatCoord = (p: LatLng) =>
  `${p.lat.toFixed(3)}°N, ${p.lng.toFixed(3)}°E`;

const marksLambdaSlider = [
  { value: 0, label: "0" },
  { value: 1, label: "1" },
];

const marksSmoothingSlider = [
  { value: 0, label: "0 m" },
  { value: 100, label: "100 m" },
];

const RouteControls = ({
  startPoint,
  endPoint,
  pickMode,
  onPickModeChange,
  showCorridor,
  onShowCorridorChange,
  onClearStart,
  onClearEnd,
  onGenerate,
  runId,
  gpxDownloadUrl,
  geojsonDownloadUrl,
}: RouteControlsProps) => {
  const DEFAULT_LAMBDA_WEIGHT = 0.7;
  const DEFAULT_SMOOTH_THRESHOLD = 8;
  const DEFAULT_SHOW_CORRIDOR = false;

  const [lambdaWeight, setLambdaWeight] = useState(DEFAULT_LAMBDA_WEIGHT);
  const [smoothThreshold, setSmoothThreshold] = useState(
    DEFAULT_SMOOTH_THRESHOLD
  );
  const [routeInputsDirty, setRouteInputsDirty] = useState(false);

  useEffect(() => {
    setRouteInputsDirty(false);
  }, [runId]);

  const handleDownloadGPX = async () => {
    if (!runId) return;
    try {
      const API = import.meta.env.VITE_API_BASE_URL;
      const downloadUrl = gpxDownloadUrl ?? `${API}/runs_output/${runId}/route.gpx`;
      const response = await fetch(downloadUrl);
      if (!response.ok) throw new Error("Failed to download GPX");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "route.gpx";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading GPX:", error);
    }
  };

  const handleDownloadGeoJSON = async () => {
    if (!runId) return;
    try {
      const API = import.meta.env.VITE_API_BASE_URL;
      const downloadUrl =
        geojsonDownloadUrl ?? `${API}/runs_output/${runId}/route.geojson`;
      const response = await fetch(downloadUrl);
      if (!response.ok) throw new Error("Failed to download GeoJSON");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "route.geojson";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading GeoJSON:", error);
    }
  };

  const resetRoutingParameters = () => {
    setRouteInputsDirty(true);
    setLambdaWeight(DEFAULT_LAMBDA_WEIGHT);
    setSmoothThreshold(DEFAULT_SMOOTH_THRESHOLD);
    onShowCorridorChange(DEFAULT_SHOW_CORRIDOR);
    onClearStart();
    onClearEnd();
  };

  return (
    <Box sx={{ p: 2, display: "flex", flexDirection: "column", flex: 1 }}>
      {/* Start point row */}
      <Box sx={{ mb: { xs: 1.5, sm: 2 } }}>
        <Typography fontSize={{xs: 12, sm: 14}} sx={{ color: "white", mb: 1 }}>
          Choose start point
        </Typography>

        <Box
          sx={{
            display: "flex",
            gap: 1,
            alignItems: "center",
            flexDirection: "row"
          }}
        >
          <Button
            variant="outlined"
            fullWidth
            onClick={() => {
              setRouteInputsDirty(true);
              onPickModeChange("start");
            }}
            sx={{
              flex: 4,
              fontSize: {xs: 12, sm: 14},
              borderColor: "#367E98",
              color: "white",
              "&:hover": {
                borderColor: "#367E98",
                backgroundColor: "rgba(54,126,152,0.10)",
              },
            }}
          >
            {pickMode === "start"
              ? "Click on map..."
              : startPoint
              ? "Re-pick start point"
              : "Pick start point"}
          </Button>

          <Button
            variant="outlined"
            disabled={!startPoint}
            onClick={() => {
              setRouteInputsDirty(true);
              onClearStart();
            }}
            sx={{
              borderColor: "rgba(255,255,255,0.35)",
              color: "white",
              flex: 1,
              fontSize: {xs: 12, sm: 14},
              "&:hover": { backgroundColor: "rgba(255,255,255,0.08)" },
              "&.Mui-disabled": {
                color: "rgba(255,255,255,0.25)",
                borderColor: "rgba(255,255,255,0.18)",
              },
            }}
          >
            Clear
          </Button>
        </Box>

        <Typography
          sx={{
            mt: 0.8,
            ml: 0.8,
            fontSize: {xs: 10, sm: 12},
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Coordinates:{" "}
          {startPoint ? formatCoord(startPoint) : "No start point selected"}
        </Typography>
      </Box>

      {/* End point row */}
      <Box sx={{ mb: { xs: 1.5, sm: 2 } }}>
        <Typography fontSize={{xs: 12, sm: 14}} sx={{ color: "white", mb: 1 }}>
          Choose end point
        </Typography>

        <Box
          sx={{
            display: "flex",
            gap: 1,
            alignItems: "center",
            flexDirection: "row"
          }}
        >
          <Button
            variant="outlined"
            fullWidth
            onClick={() => {
              setRouteInputsDirty(true);
              onPickModeChange("end");
            }}
            sx={{
              borderColor: "#EE7B04",
              color: "white",
              fontSize: {xs: 12, sm: 14},
              flex: 4,
              "&:hover": {
                borderColor: "#EE7B04",
                backgroundColor: "rgba(54,126,152,0.10)",
              },
            }}
          >
            {pickMode === "end"
              ? "Click on map..."
              : endPoint
              ? "Re-pick end point"
              : "Pick end point"}
          </Button>

          <Button
            variant="outlined"
            disabled={!endPoint}
            onClick={() => {
              setRouteInputsDirty(true);
                   onClearEnd();
            }}
            sx={{
              borderColor: "rgba(255,255,255,0.35)",
              color: "white",
              flex: 1,
              fontSize: {xs: 12, sm: 14},
              "&:hover": { backgroundColor: "rgba(255,255,255,0.08)" },
              "&.Mui-disabled": {
                color: "rgba(255,255,255,0.25)",
                borderColor: "rgba(255,255,255,0.18)",
              },
            }}
          >
            Clear
          </Button>
        </Box>

        <Typography
          sx={{
            mt: 0.8,
            ml: 0.8,
            fontSize: {xs: 10, sm: 12},
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Coordinates:{" "}
          {endPoint ? formatCoord(endPoint) : "No end point selected"}
        </Typography>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)", mb: { xs: 1.5, sm: 2 } }} />

      <Box >
        <Typography fontSize={{xs: 12, sm: 14}} sx={{ color: "white", mb: 0.3 }}>
          Choose lambda weight
        </Typography>
        <Typography
          sx={{
            ml: 0.8,
            fontSize: {xs: 10, sm: 12},
            color: "rgba(255,255,255,0.75)",
          }}
        >
          More importance to cost friction vs distance.
        </Typography>
        <Box sx={{ px: 2 }}>
          <Slider
            value={lambdaWeight}
            onChange={(_, val) => {
              setRouteInputsDirty(true);
              setLambdaWeight(val as number);
            }}
            valueLabelDisplay="auto"
            min={0}
            max={1}
            step={0.01}
            marks={marksLambdaSlider}
            sx={{
              color: "#367E98",
              "& .MuiSlider-thumb": { width: { xs: 12, sm: 16 }, height: { xs: 12, sm: 16 } },
              "& .MuiSlider-mark": {
                backgroundColor: "#367E98",
              },

              "& .MuiSlider-markLabel": {
                top: 30,
                color: "rgba(255,255,255,0.65)",
                fontSize: {xs: 10, sm: 12},
              },
            }}
          />
        </Box>
      </Box>

      <Box>
        <Typography fontSize={{xs: 12, sm: 14}} sx={{ color: "white", mb: 0.3 }}>
          Choose smoothing threshold
        </Typography>
        <Typography
          sx={{
            ml: 0.8,
            fontSize: {xs: 10, sm: 12},
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Max deviation [m] from route when simplifying.
        </Typography>
        <Box sx={{ px: 2 }}>
          <Slider
            value={smoothThreshold}
            onChange={(_, val) => {
              setRouteInputsDirty(true);
              setSmoothThreshold(val as number);
            }}
            valueLabelDisplay="auto"
            min={0}
            max={100}
            step={1}
            marks={marksSmoothingSlider}
            sx={{
              color: "#367E98",
              "& .MuiSlider-thumb": { width: { xs: 12, sm: 16 }, height: { xs: 12, sm: 16 } },
              "& .MuiSlider-mark": {
                backgroundColor: "#367E98",
              },

              "& .MuiSlider-markLabel": {
                top: 34,
                color: "rgba(255,255,255,0.65)",
                fontSize: {xs: 10, sm: 12},
              },
            }}
          />
        </Box>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)", mb: 1, mt: { xs: 0, sm: 1 } }} />

      <FormControlLabel
        label={
          <Typography
            fontSize={{xs: 12, sm: 14}}
            sx={{ color: "rgba(255,255,255,0.85)" }}
          >
            Show area of possible route choices
          </Typography>
        }
        control={
          <Checkbox
            checked={showCorridor}
            onChange={(e) => {
              onShowCorridorChange(e.target.checked);
            }}
            sx={{
              color: "rgba(255,255,255,0.55)",
              "&.Mui-checked": { color: "#367E98" },
              pl: 0,
            }}
          />
        }
        sx={{ m: 0 }}
      />

      <Box sx={{ display: "flex", mb: { xs: 1, sm: 1.5 }, mt: "auto" }}>
        <Button
          variant="contained"
          fullWidth
          disabled={!startPoint || !endPoint || pickMode !== null}
          onClick={() => {
            setRouteInputsDirty(false);
            onGenerate({ lambdaWeight, smoothThreshold });
          }}
          size="large"
          sx={{
            backgroundColor: "#EE7B04",
            fontSize: {xs: 14, sm: 16},
            "&:hover": { transform: "scale(1.01)" },
          }}
        >
          Generate route
        </Button>
      </Box>

      {runId && !routeInputsDirty && pickMode === null && startPoint && endPoint && (
        <Stack
          direction="row"
          spacing={1}
          justifyContent="center"
          sx={{ mb: { xs: 1, sm: 1.5 }, mx: 1 }}
        >
          <Button
            variant="outlined"
            fullWidth
            startIcon={<FileDownloadIcon />}
            onClick={handleDownloadGPX}
            size="small"
            sx={{
              borderColor: "#367E98",
              color: "white",
              fontSize: {xs: 12, sm: 14},
              "&:hover": {
                backgroundColor: "rgba(54,126,152,0.10)",
                borderColor: "#367E98",
              },
            }}
          >
            GPX
          </Button>
          <Button
            variant="outlined"
            fullWidth
            startIcon={<FileDownloadIcon />}
            onClick={handleDownloadGeoJSON}
            size="small"
            sx={{
              borderColor: "#367E98",
              color: "white",
              fontSize: {xs: 12, sm: 14},
              "&:hover": {
                backgroundColor: "rgba(54,126,152,0.10)",
                borderColor: "#367E98",
              },
            }}
          >
            GeoJSON
          </Button>
        </Stack>
      )}

      <Box sx={{ display: "flex", justifyContent: "center", mt: { xs: 1, sm: 1.5 } }}>
        <Button
          variant="outlined"
          onClick={resetRoutingParameters}
          disabled={
            startPoint === null &&
            endPoint === null &&
            lambdaWeight === DEFAULT_LAMBDA_WEIGHT &&
            smoothThreshold === DEFAULT_SMOOTH_THRESHOLD &&
            showCorridor === DEFAULT_SHOW_CORRIDOR
          }
          size="small"
          sx={{
            borderColor: "rgba(255,255,255,0.35)",
            color: "white",
            fontSize: {xs: 12, sm: 14},
            "&:hover": {
              backgroundColor: "rgba(255,255,255,0.08)",
            },
            "&.Mui-disabled": {
              color: "rgba(255,255,255,0.25)",
              borderColor: "rgba(255,255,255,0.18)",
            },
          }}
        >
          Reset routing parameters
        </Button>
      </Box>
    </Box>
  );
};

export default RouteControls;
