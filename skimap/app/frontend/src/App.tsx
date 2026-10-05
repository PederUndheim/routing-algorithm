import { useEffect, useState, useSyncExternalStore } from "react";

import Alert from "@mui/material/Alert";
import Backdrop from "@mui/material/Backdrop";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";

import { checkHealth, requestCrux, requestRoute } from "./api";
import { DEFAULT_BASEMAP } from "./layers/basemaps";
import type { BasemapId } from "./layers/basemaps";
import { DEFAULT_OPACITY, OVERLAYS_OFF } from "./layers/overlays";
import type { OverlayId } from "./layers/overlays";
import MapView from "./map/MapView";
import { createRouteList } from "./routes/routeList";
import RoutePanel from "./routing/RoutePanel";
import { usePanelWidth } from "./routing/usePanelWidth";
import type { LatLng, MapFocus, PickMode } from "./types";

const App = () => {
  const [basemap, setBasemap] = useState<BasemapId>(DEFAULT_BASEMAP);
  const [overlays, setOverlays] = useState<Record<OverlayId, boolean>>(OVERLAYS_OFF);
  const [overlayOpacity, setOverlayOpacity] =
    useState<Record<OverlayId, number>>(DEFAULT_OPACITY);

  const [panelOpen, setPanelOpen] = useState(true);
  // Here rather than in the drawer, because the map insets what it zooms to
  // by the drawer's width and has to follow it as it is dragged.
  const { width: panelWidth, setWidth: setPanelWidth, resetWidth } = usePanelWidth();
  const [startPoint, setStartPoint] = useState<LatLng | null>(null);
  const [endPoint, setEndPoint] = useState<LatLng | null>(null);
  const [pickMode, setPickMode] = useState<PickMode>(null);

  // Moving either point leaves every Route alone. They are in the list to be
  // compared, not tied to the markers that happen to be on the map now.
  const [routeList] = useState(createRouteList);
  const { routes, selectedId } = useSyncExternalStore(
    routeList.subscribe,
    routeList.getState
  );
  const selected = routes.find((r) => r.id === selectedId) ?? null;
  const [focus, setFocus] = useState<MapFocus | null>(null);

  const [showCorridor, setShowCorridor] = useState(true);
  // Half strength by default: the style is solid along the route, and the
  // terrain under it is usually the reason you are looking at the corridor.
  const [corridorOpacity, setCorridorOpacity] = useState(0.5);
  const [isRouting, setIsRouting] = useState(false);
  const [isIdentifying, setIsIdentifying] = useState(false);
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

  const generate = async () => {
    if (!startPoint || !endPoint) return;

    setIsRouting(true);
    setErrorMsg(null);
    try {
      const route = routeList.addRouted(await requestRoute(startPoint, endPoint));
      setFocus({ kind: "route", line: route.line });
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

  // The result goes to the Route it was asked for, by id, even if another
  // one has been selected by the time it comes back.
  const identify = async () => {
    if (!selected) return;
    const { id, line } = selected;

    setIsIdentifying(true);
    setErrorMsg(null);
    try {
      routeList.attachCrux(id, await requestCrux(line));
      setBackendReady(true);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Identifying cruxes failed.");
      if (err instanceof TypeError) setBackendReady(false);
    } finally {
      setIsIdentifying(false);
    }
  };

  const upload = async (files: File[]) => {
    const { added, errors } = await routeList.upload(files);
    if (added.length > 0) setFocus({ kind: "route", line: added[added.length - 1].line });
    if (errors.length > 0) {
      setErrorMsg(errors.map((e) => `${e.fileName}: ${e.reason}`).join("\n"));
    }
  };

  // Only the Selected route's corridor, and only while it is on the map:
  // several overlapping bands would make the terrain under them unreadable.
  const corridor = selected?.visible ? (selected.routed?.corridor ?? null) : null;

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
        panelWidth={panelWidth}
        onOpenPanel={() => setPanelOpen(true)}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        startPoint={startPoint}
        endPoint={endPoint}
        onStartPointChange={setStartPoint}
        onEndPointChange={setEndPoint}
        routes={routes}
        selectedId={selectedId}
        onSelectRoute={routeList.select}
        focus={focus}
        onDropFiles={upload}
        corridor={corridor}
        showCorridor={showCorridor}
        corridorOpacity={corridorOpacity}
      />

      <RoutePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        panelWidth={panelWidth}
        onPanelWidthChange={setPanelWidth}
        onResetPanelWidth={resetWidth}
        startPoint={startPoint}
        endPoint={endPoint}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        onClearStart={() => setStartPoint(null)}
        onClearEnd={() => setEndPoint(null)}
        onGenerate={generate}
        isRouting={isRouting}
        backendReady={backendReady}
        routes={routes}
        selectedId={selectedId}
        onSelectRoute={routeList.select}
        onToggleRoute={routeList.toggleVisible}
        onDeleteRoute={routeList.remove}
        onUpload={upload}
        isIdentifying={isIdentifying}
        onIdentify={identify}
        onFocusCrux={(routeId, crux) =>
          setFocus({ kind: "crux", routeId, number: crux.number, position: crux.position })
        }
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
          // An upload reports one line per bad file.
          sx={{ width: "100%", whiteSpace: "pre-line" }}
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
