import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Slider from "@mui/material/Slider";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";

import { useState } from "react";

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
}: RouteControlsProps) => {
  const DEFAULT_LAMBDA_WEIGHT = 0.7;
  const DEFAULT_SMOOTH_THRESHOLD = 8;
  const DEFAULT_SHOW_CORRIDOR = false;

  const [lambdaWeight, setLambdaWeight] = useState(DEFAULT_LAMBDA_WEIGHT);
  const [smoothThreshold, setSmoothThreshold] = useState(
    DEFAULT_SMOOTH_THRESHOLD
  );

  const resetRoutingParameters = () => {
    setLambdaWeight(DEFAULT_LAMBDA_WEIGHT);
    setSmoothThreshold(DEFAULT_SMOOTH_THRESHOLD);
    onShowCorridorChange(DEFAULT_SHOW_CORRIDOR);
    onClearStart();
    onClearEnd();
  };

  return (
    <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 3 }}>
      {/* Start point row */}
      <Box>
        <Typography variant="subtitle2" sx={{ color: "white", mb: 1 }}>
          Choose start point
        </Typography>

        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Button
            variant="outlined"
            fullWidth
            onClick={() => onPickModeChange("start")}
            sx={{
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
            onClick={onClearStart}
            sx={{
              minWidth: 90,
              borderColor: "rgba(255,255,255,0.35)",
              color: "white",
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
            fontSize: 12,
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Coordinates:{" "}
          {startPoint ? formatCoord(startPoint) : "No start point selected"}
        </Typography>
      </Box>

      {/* End point row */}
      <Box>
        <Typography variant="subtitle2" sx={{ color: "white", mb: 1 }}>
          Choose end point
        </Typography>

        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <Button
            variant="outlined"
            fullWidth
            onClick={() => onPickModeChange("end")}
            sx={{
              borderColor: "#EE7B04",
              color: "white",
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
            onClick={onClearEnd}
            sx={{
              minWidth: 90,
              borderColor: "rgba(255,255,255,0.35)",
              color: "white",
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
            fontSize: 12,
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Coordinates:{" "}
          {endPoint ? formatCoord(endPoint) : "No end point selected"}
        </Typography>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)" }} />

      <Box>
        <Typography variant="subtitle2" sx={{ color: "white" }}>
          Choose lambda weight
        </Typography>
        <Typography
          sx={{
            mt: 0.8,
            ml: 0.8,
            fontSize: 12,
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Higher values give more importance to cost friction vs distance.
        </Typography>
        <Box sx={{ px: 2 }}>
          <Slider
            value={lambdaWeight}
            onChange={(_, val) => setLambdaWeight(val as number)}
            valueLabelDisplay="auto"
            min={0}
            max={1}
            step={0.01}
            marks={marksLambdaSlider}
            sx={{
              color: "#367E98",
              "& .MuiSlider-thumb": { width: 16, height: 16 },
              "& .MuiSlider-mark": {
                backgroundColor: "#367E98",
              },

              "& .MuiSlider-markLabel": {
                color: "rgba(255,255,255,0.65)",
                fontSize: 12,
              },
            }}
          />
        </Box>
      </Box>

      <Box>
        <Typography variant="subtitle2" sx={{ color: "white" }}>
          Choose smoothing threshold
        </Typography>
        <Typography
          sx={{
            mt: 0.8,
            ml: 0.8,
            fontSize: 12,
            color: "rgba(255,255,255,0.75)",
          }}
        >
          Maximal allowed deviation (in meters) from original route when
          simplifying route.
        </Typography>
        <Box sx={{ px: 2 }}>
          <Slider
            value={smoothThreshold}
            onChange={(_, val) => setSmoothThreshold(val as number)}
            valueLabelDisplay="auto"
            min={0}
            max={100}
            step={1}
            marks={marksSmoothingSlider}
            sx={{
              color: "#367E98",
              "& .MuiSlider-thumb": { width: 16, height: 16 },
              "& .MuiSlider-mark": {
                backgroundColor: "#367E98",
              },

              "& .MuiSlider-markLabel": {
                color: "rgba(255,255,255,0.65)",
                fontSize: 12,
              },
            }}
          />
        </Box>
      </Box>

      <FormControlLabel
        label={
          <Typography sx={{ color: "rgba(255,255,255,0.85)", fontSize: 14 }}>
            Show corridor
          </Typography>
        }
        control={
          <Checkbox
            checked={showCorridor}
            onChange={(e) => onShowCorridorChange(e.target.checked)}
            sx={{
              color: "rgba(255,255,255,0.55)",
              "&.Mui-checked": { color: "#367E98" },
            }}
          />
        }
        sx={{ m: 0 }}
      />

      <Box sx={{ display: "flex" }}>
        <Button
          variant="contained"
          fullWidth
          disabled={!startPoint || !endPoint || pickMode !== null}
          onClick={() => onGenerate({ lambdaWeight, smoothThreshold })}
          size="large"
          sx={{
            backgroundColor: "#EE7B04",
            "&:hover": { transform: "scale(1.01)" },
          }}
        >
          Generate route
        </Button>
      </Box>

      <Box sx={{ display: "flex", justifyContent: "center" }}>
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
