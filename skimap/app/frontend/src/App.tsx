import { useCallback, useEffect, useState } from "react";

import Alert from "@mui/material/Alert";
import Backdrop from "@mui/material/Backdrop";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";

import { checkHealth, requestRoute } from "./api";
import { DEFAULT_BASEMAP } from "./layers/basemaps";
import type { BasemapId } from "./layers/basemaps";
import { DEFAULT_OPACITY, OVERLAYS_OFF } from "./layers/overlays";
import type { OverlayId } from "./layers/overlays";
import MapView from "./map/MapView";
import RoutePanel from "./routing/RoutePanel";
import type { LatLng, PickMode, RouteResponse } from "./types";

const App = () => {
  const [basemap, setBasemap] = useState<BasemapId>(DEFAULT_BASEMAP);
  const [overlays, setOverlays] = useState<Record<OverlayId, boolean>>(OVERLAYS_OFF);
  const [overlayOpacity, setOverlayOpacity] =
    useState<Record<OverlayId, number>>(DEFAULT_OPACITY);

  const [panelOpen, setPanelOpen] = useState(true);
  const [startPoint, setStartPoint] = useState<LatLng | null>(null);
  const [endPoint, setEndPoint] = useState<LatLng | null>(null);
  const [pickMode, setPickMode] = useState<PickMode>(null);

  const [result, setResult] = useState<RouteResponse | null>(null);
  const [showCorridor, setShowCorridor] = useState(true);
  // Half strength by default: the style is solid along the route, and the
  // terrain under it is usually the reason you are looking at the corridor.
  const [corridorOpacity, setCorridorOpacity] = useState(0.5);
  const [isRouting, setIsRouting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // null until the first ping answers, so the panel does not flash a
  // "not reachable" warning before it has asked.
  const [backendReady, setBackendReady] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    checkHealth().then((ok) => {
      if (!cancelled) setBackendReady(ok);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // A route belongs to the pair of points that produced it. Moving either one
  // makes it stale, so it goes rather than sitting on the map as a line that
  // no longer starts where the marker does.
  const setStart = useCallback((point: LatLng) => {
    setStartPoint(point);
    setResult(null);
  }, []);

  const setEnd = useCallback((point: LatLng) => {
    setEndPoint(point);
    setResult(null);
  }, []);

  const clearStart = useCallback(() => {
    setStartPoint(null);
    setResult(null);
  }, []);

  const clearEnd = useCallback(() => {
    setEndPoint(null);
    setResult(null);
  }, []);

  const generate = async () => {
    if (!startPoint || !endPoint) return;

    setIsRouting(true);
    setErrorMsg(null);
    setResult(null);
    try {
      setResult(await requestRoute(startPoint, endPoint));
      setBackendReady(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Routing failed.");
      // A network-level failure means the server is not there; a 400 from the
      // server itself is a bad request, not a dead backend.
      if (err instanceof TypeError) setBackendReady(false);
    } finally {
      setIsRouting(false);
    }
  };

  return (
    <div style={{ height: "100dvh" }}>
      <MapView
        basemap={basemap}
        onBasemapChange={setBasemap}
        overlays={overlays}
        onToggleOverlay={(id) => setOverlays((prev) => ({ ...prev, [id]: !prev[id] }))}
        overlayOpacity={overlayOpacity}
        onOverlayOpacityChange={(id, opacity) =>
          setOverlayOpacity((prev) => ({ ...prev, [id]: opacity }))
        }
        panelOpen={panelOpen}
        onOpenPanel={() => setPanelOpen(true)}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        startPoint={startPoint}
        endPoint={endPoint}
        onStartPointChange={setStart}
        onEndPointChange={setEnd}
        routeGeoJson={result?.route ?? null}
        corridor={result?.corridor ?? null}
        showCorridor={showCorridor}
        corridorOpacity={corridorOpacity}
      />

      <RoutePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        startPoint={startPoint}
        endPoint={endPoint}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        onClearStart={clearStart}
        onClearEnd={clearEnd}
        onGenerate={generate}
        isRouting={isRouting}
        backendReady={backendReady}
        result={result}
        showCorridor={showCorridor}
        onShowCorridorChange={setShowCorridor}
        corridorOpacity={corridorOpacity}
        onCorridorOpacityChange={setCorridorOpacity}
      />

      <Snackbar
        open={Boolean(errorMsg)}
        autoHideDuration={8000}
        onClose={() => setErrorMsg(null)}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
      >
        <Alert
          onClose={() => setErrorMsg(null)}
          severity="error"
          variant="filled"
          sx={{ width: "100%" }}
        >
          {errorMsg}
        </Alert>
      </Snackbar>

      <Backdrop open={isRouting} sx={{ zIndex: 2000, color: "#fff" }}>
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
          <CircularProgress color="inherit" />
          <Typography>Routing. Two cost spreads over the surface - a few seconds.</Typography>
        </Box>
      </Backdrop>
    </div>
  );
};

export default App;
