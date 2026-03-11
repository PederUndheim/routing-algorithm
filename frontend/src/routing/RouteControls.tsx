import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Slider from "@mui/material/Slider";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import Collapse from "@mui/material/Collapse";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import AddIcon from "@mui/icons-material/Add";
import EditLocationAltIcon from "@mui/icons-material/EditLocationAlt";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";

import { useEffect, useState } from "react";

import type { LatLng, PickMode } from "../types/mapTypes";
import type { CorridorMode } from "../types/corridor";

type RouteControlsProps = {
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
  onGenerate: (params: {
    lambdaWeight: number;
    smoothThreshold: number;
    avoidLake: boolean;
    avoidGlacier: boolean;
    trackInfluenceMode: "off" | "forest_only" | "balanced" | "strong";
    corridorMode: "conservative" | "balanced" | "explorative";
    stopPoints: LatLng[];
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

const MAX_STOPS = 3;

type TrackInfluenceMode = "off" | "forest_only" | "balanced" | "strong";
const compactRadioSx = {
  p: 0.25,
  mr: 0.10,
  color: "rgba(255,255,255,0.55)",
  "& .MuiSvgIcon-root": { fontSize: 18 },
  "&.Mui-checked": { color: "#367E98" },
};

const compactLabelSx = {
  m: 0.1,
  "& .MuiFormControlLabel-label": { lineHeight: 1.1 },
};

const RouteControls = ({
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
  onGenerate,
  runId,
  gpxDownloadUrl,
  geojsonDownloadUrl,
}: RouteControlsProps) => {
  const DEFAULT_LAMBDA_WEIGHT = 0.55;
  const DEFAULT_SMOOTH_THRESHOLD = 8;
  const DEFAULT_SHOW_CORRIDOR = false;
  const DEFAULT_AVOID_LAKE = false;
  const DEFAULT_AVOID_GLACIER = false;
  const DEFAULT_TRACK_INFLUENCE_MODE: TrackInfluenceMode = "balanced";
  const DEFAULT_CORRIDOR_MODE: CorridorMode = "balanced";

  const [lambdaWeight, setLambdaWeight] = useState(DEFAULT_LAMBDA_WEIGHT);
  const [smoothThreshold, setSmoothThreshold] = useState(
    DEFAULT_SMOOTH_THRESHOLD
  );
  const [avoidLake, setAvoidLake] = useState(DEFAULT_AVOID_LAKE);
  const [avoidGlacier, setAvoidGlacier] = useState(DEFAULT_AVOID_GLACIER);
  const [trackInfluenceMode, setTrackInfluenceMode] =
    useState<TrackInfluenceMode>(DEFAULT_TRACK_INFLUENCE_MODE);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [routeInputsDirty, setRouteInputsDirty] = useState(false);
  const hasReachedMaxStops = stopPoints.length >= MAX_STOPS;

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
    setAvoidLake(DEFAULT_AVOID_LAKE);
    setAvoidGlacier(DEFAULT_AVOID_GLACIER);
    setTrackInfluenceMode(DEFAULT_TRACK_INFLUENCE_MODE);
    onCorridorModeChange(DEFAULT_CORRIDOR_MODE);
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

      <Box sx={{ mb: { xs: 1, sm: 1 }, mx: { xs: 1, sm: 1.5 } }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={<AddIcon />}
            disabled={hasReachedMaxStops}
            onClick={() => {
              setRouteInputsDirty(true);
              if (pickMode === "stop") {
                onPickModeChange(null);
              } else {
                onRequestAddStop();
              }
            }}
            sx={{
              borderColor: "rgba(255,255,255,0.35)",
              color: "white",
              fontSize: { xs: 11, sm: 12 },
              minWidth: "auto",
              px: 1,
              "&.Mui-disabled": {
                color: "rgba(255,255,255,0.45)",
                borderColor: "rgba(255,255,255,0.2)",
              },
            }}
          >
            {hasReachedMaxStops
              ? `Maximum ${MAX_STOPS} stops`
              : pickMode === "stop"
              ? "Click on map..."
              : "Add stop"}
          </Button>
        </Box>

        {stopPoints.length > 0 && (
          <Stack spacing={0.8}>
            {stopPoints.map((stopPoint, index) => (
              <Box
                key={`stop-control-${index}`}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0.2,
                  px: 1,
                  py: 0.7,
                  borderRadius: 1.5,
                  backgroundColor: "rgba(255,255,255,0.06)",
                }}
              >
                <Box
                  sx={{
                    width: 22,
                    height: 22,
                    mr: 1,
                    borderRadius: "50%",
                    border: "1px solid rgba(255,255,255,0.35)",
                    backgroundColor: "#555555",
                    color: "white",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  {index + 1}
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography fontSize={{ xs: 11, sm: 13 }} sx={{ color: "white" }}>
                    Stop {index + 1}
                  </Typography>
                  <Typography sx={{ fontSize: { xs: 9, sm: 11 }, color: "rgba(255,255,255,0.75)" }}>
                    {formatCoord(stopPoint)}
                  </Typography>
                </Box>
                <IconButton
                  size="small"
                  disabled={index === 0}
                  onClick={() => {
                    setRouteInputsDirty(true);
                    onMoveStop(index, index - 1);
                  }}
                  sx={{
                    color: "rgba(255,255,255,0.8)",
                    "&.Mui-disabled": {
                      color: "rgba(255,255,255,0.25)",
                    },
                  }}
                >
                  <KeyboardArrowUpIcon sx={{ color: "inherit", fontSize: 18 }} />
                </IconButton>
                <IconButton
                  size="small"
                  disabled={index === stopPoints.length - 1}
                  onClick={() => {
                    setRouteInputsDirty(true);
                    onMoveStop(index, index + 1);
                  }}
                  sx={{
                    color: "rgba(255,255,255,0.8)",
                    "&.Mui-disabled": {
                      color: "rgba(255,255,255,0.25)",
                    },
                  }}
                >
                  <KeyboardArrowDownIcon sx={{ color: "inherit", fontSize: 18 }} />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => {
                    setRouteInputsDirty(true);
                    onRequestRepickStop(index);
                  }}
                >
                  <EditLocationAltIcon sx={{ color: "rgba(255,255,255,0.8)", fontSize: 18 }} />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => {
                    setRouteInputsDirty(true);
                    onRemoveStop(index);
                  }}
                >
                  <DeleteOutlineIcon sx={{ color: "rgba(255,255,255,0.8)", fontSize: 18 }} />
                </IconButton>
              </Box>
            ))}
          </Stack>
        )}
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

      <Box>
        <Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "white", mb: { xs: 0.8, sm: 1 } }}>
          Existing track data influence
        </Typography>
        <RadioGroup
          row
          value={trackInfluenceMode}
          onChange={(e) => {
            setRouteInputsDirty(true);
            setTrackInfluenceMode(e.target.value as TrackInfluenceMode);
          }}
          sx={{ mb: 0.6, columnGap: { xs: 0.6, sm: 1 }, rowGap: 0.2, flexWrap: "wrap" }}
        >
          <FormControlLabel
            value="off"
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Off</Typography>}
            sx={compactLabelSx}
          />
          <FormControlLabel
            value="forest_only"
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Forest only</Typography>}
            sx={compactLabelSx}
          />
          <FormControlLabel
            value="balanced"
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Balanced</Typography>}
            sx={compactLabelSx}
          />
          <FormControlLabel
            value="strong"
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Strong</Typography>}
            sx={compactLabelSx}
          />
        </RadioGroup>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)", mb: { xs: 1.5, sm: 2 }, mt: { xs: 0.5, sm: 2 } }} />

      <Box> 
        <Typography fontSize={{xs: 12, sm: 14}} sx={{ color: "white", mb: { xs: 0, sm: 0.5 } }}>
          Make routing restrictions?
        </Typography> 
        <Stack direction="row" sx={{ mb: 1 }}>
          <FormControlLabel
            label={
              <Typography
                fontSize={{xs: 12, sm: 14}}
                sx={{ color: "rgba(255,255,255,0.85)" }}
              >
                Avoid lakes
              </Typography>
            }
            control={
              <Checkbox
                checked={avoidLake}
                onChange={(e) => {
                  setRouteInputsDirty(true);
                  setAvoidLake(e.target.checked);
                }}
                sx={{
                  color: "rgba(255,255,255,0.55)",
                  "&.Mui-checked": { color: "#367E98" },
                  pl: 0,
                }}
              />
            }
            sx={{ m: 0, flex: 1 }}
          />

          <FormControlLabel
            label={
              <Typography
                fontSize={{xs: 12, sm: 14}}
                sx={{ color: "rgba(255,255,255,0.85)" }}
              >
                Avoid glaciers
              </Typography>
            }
            control={
              <Checkbox
                checked={avoidGlacier}
                onChange={(e) => {
                  setRouteInputsDirty(true);
                  setAvoidGlacier(e.target.checked);
                }}
                sx={{
                  color: "rgba(255,255,255,0.55)",
                  "&.Mui-checked": { color: "#367E98" },
                  pl: 0,
                }}
              />
            }
            sx={{ m: 0, flex: 1 }}
          />
        </Stack>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)", mb: { xs: 0.5, sm: 1 }, mt: { xs: 0, sm: 0.5 } }} />


      <Button
        variant="text"
        onClick={() => setShowAdvancedSettings((prev) => !prev)}
        startIcon={showAdvancedSettings ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
        sx={{
          justifyContent: "flex-start",
          color: "white",
          textTransform: "none",
          fontSize: { xs: 12, sm: 14 },
          px: 0,
          mb: 1,
          "&:hover": {
            backgroundColor: "transparent",
          },
        }}
      >
        Advanced routing settings
      </Button>

      <Collapse in={showAdvancedSettings} timeout="auto" unmountOnExit sx={{ mb: { xs: 1, sm: 2 } }}>
        <Box>
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
      </Collapse>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)", mb: { xs: 1, sm: 1.5 } }} />

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

      <Box
        sx={{
          ml: { xs: 0.5, sm: 1 },
          mt: 0.2,
          mb: 3,
          opacity: showCorridor ? 1 : 0.45,
          pointerEvents: showCorridor ? "auto" : "none",
          transition: "opacity 0.15s ease",
        }}
      >
        <Typography fontSize={{ xs: 11, sm: 13 }} sx={{ color: "rgba(255,255,255,0.80)", mb: 0.4 }}>
          Corridor style
        </Typography>
        <RadioGroup
          row
          value={corridorMode}
          onChange={(e) => {
            onCorridorModeChange(e.target.value as CorridorMode);
          }}
          sx={{ mt: 0.2, columnGap: { xs: 0.6, sm: 1 }, rowGap: 0.2, flexWrap: "wrap" }}
        >
          <FormControlLabel
            value="conservative"
            disabled={!showCorridor}
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Conservative</Typography>}
            sx={compactLabelSx}
          />
          <FormControlLabel
            value="balanced"
            disabled={!showCorridor}
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Balanced</Typography>}
            sx={compactLabelSx}
          />
          <FormControlLabel
            value="explorative"
            disabled={!showCorridor}
            control={<Radio size="small" sx={compactRadioSx} />}
            label={<Typography fontSize={{ xs: 12, sm: 14 }} sx={{ color: "rgba(255,255,255,0.85)" }}>Explorative</Typography>}
            sx={compactLabelSx}
          />
        </RadioGroup>
      </Box>

      <Box sx={{ display: "flex", mb: { xs: 1, sm: 1.5 }, mt: "auto" }}>
        <Button
          variant="contained"
          fullWidth
          disabled={!startPoint || !endPoint || pickMode !== null}
          onClick={() => {
            setRouteInputsDirty(false);
            onGenerate({
              lambdaWeight,
              smoothThreshold,
              avoidLake,
              avoidGlacier,
              trackInfluenceMode,
              corridorMode,
              stopPoints,
            });
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
            avoidLake === DEFAULT_AVOID_LAKE &&
            avoidGlacier === DEFAULT_AVOID_GLACIER &&
            trackInfluenceMode === DEFAULT_TRACK_INFLUENCE_MODE &&
            corridorMode === DEFAULT_CORRIDOR_MODE &&
            stopPoints.length === 0 &&
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
