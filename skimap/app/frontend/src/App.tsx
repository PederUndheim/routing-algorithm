import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import Alert from "@mui/material/Alert";
import Backdrop from "@mui/material/Backdrop";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";

import { checkHealth, requestCrux, requestRoute } from "./api";
import { defaultsAt } from "./crux/assessment";
import { DEFAULT_BASEMAP } from "./layers/basemaps";
import type { BasemapId } from "./layers/basemaps";
import { DEFAULT_OPACITY, DEFAULT_OVERLAYS } from "./layers/overlays";
import type { OverlayId } from "./layers/overlays";
import MapView from "./map/MapView";
import { createRouteList } from "./routes/routeList";
import AddCruxDialog from "./routing/AddCruxDialog";
import RoutePanel from "./routing/RoutePanel";
import { usePanelWidth } from "./routing/usePanelWidth";
import type { AddMode, CruxEntry, LatLng, MapFocus, PickMode } from "./types";

const App = () => {
  const [basemap, setBasemap] = useState<BasemapId>(DEFAULT_BASEMAP);
  const [overlays, setOverlays] = useState<Record<OverlayId, boolean>>(DEFAULT_OVERLAYS);
  const [overlayOpacity, setOverlayOpacity] =
    useState<Record<OverlayId, number>>(DEFAULT_OPACITY);

  const [panelOpen, setPanelOpen] = useState(true);
  // Here rather than in the drawer, because the map insets what it zooms to
  // by the drawer's width and has to follow it as it is dragged.
  const { width: panelWidth, setWidth: setPanelWidth, resetWidth } = usePanelWidth();
  const [startPoint, setStartPoint] = useState<LatLng | null>(null);
  const [endPoint, setEndPoint] = useState<LatLng | null>(null);
  const [pickMode, setPickMode] = useState<PickMode>(null);
  const [addMode, setAddMode] = useState<AddMode>("generate");
  // The line being drawn. Kept when you switch to another way of adding a
  // Route and back, so a half-drawn line is not lost to a stray click.
  const [draft, setDraft] = useState<LatLng[]>([]);
  // Start drawing pressed: until then a click on the map is just a click.
  const [isDrawing, setIsDrawing] = useState(false);
  // The drawn Route the draft was opened from, or null for a new one.
  const [editingId, setEditingId] = useState<string | null>(null);

  // Moving either point leaves every Route alone. They are in the list to be
  // compared, not tied to the markers that happen to be on the map now.
  const [routeList] = useState(createRouteList);
  const { routes, selectedId } = useSyncExternalStore(
    routeList.subscribe,
    routeList.getState
  );
  const selected = routes.find((r) => r.id === selectedId) ?? null;
  // Gone if it was deleted mid-edit; the draft then saves as a new Route.
  const editing = routes.find((r) => r.id === editingId) ?? null;
  const [focus, setFocus] = useState<MapFocus | null>(null);

  // The Crux whose questions are open in the drawer. Ids are unique across
  // Routes, so one id is enough.
  const [activeCruxId, setActiveCruxId] = useState<string | null>(null);
  // Add crux pressed: the next map click picks a spot on the Selected route,
  // which then waits in the form until it is added or given up.
  const [placingCrux, setPlacingCrux] = useState(false);
  const [pendingCrux, setPendingCrux] = useState<{ position: LatLng; distance_m: number } | null>(
    null
  );

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

  const changeAddMode = (mode: AddMode) => {
    setAddMode(mode);
    if (mode !== "generate") setPickMode(null);
  };

  const finishDraft = () => {
    const coordinates = draft.map((p) => [p.lng, p.lat]);
    if (editing) {
      routeList.updateLine(editing.id, coordinates);
      routeList.select(editing.id);
    } else {
      routeList.addDrawn(coordinates);
    }
    stopDrawing();
  };

  /** Back to the normal map: the draft dropped, no Route being edited. */
  const stopDrawing = () => {
    setDraft([]);
    setEditingId(null);
    setIsDrawing(false);
  };

  /** Open a drawn Route's points for dragging about, in the Draw mode. */
  const editRoute = (id: string) => {
    const route = routes.find((r) => r.id === id);
    if (!route) return;
    setDraft(route.line.coordinates.map(([lng, lat]) => ({ lat, lng })));
    setEditingId(id);
    setIsDrawing(true);
    changeAddMode("draw");
    setPanelOpen(true);
    routeList.select(id);
    setFocus({ kind: "route", line: route.line });
  };

  const stopPlacingCrux = useCallback(() => {
    setPlacingCrux(false);
    setPendingCrux(null);
  }, []);

  const togglePlacingCrux = () => {
    if (placingCrux) {
      stopPlacingCrux();
      return;
    }
    setPickMode(null);
    setPlacingCrux(true);
  };

  const addCrux = (input: Parameters<typeof routeList.addManualCrux>[1]) => {
    if (!selected) return;
    const crux = routeList.addManualCrux(selected.id, input);
    if (crux) setActiveCruxId(crux.id);
    stopPlacingCrux();
  };

  /** From the drawer: open a Crux's questions and take the map there, or
   *  fold them away again. */
  const activateCrux = (routeId: string, crux: CruxEntry) => {
    if (crux.id === activeCruxId) {
      setActiveCruxId(null);
      return;
    }
    setActiveCruxId(crux.id);
    setFocus({ kind: "crux", routeId, number: crux.number, position: crux.position });
  };

  /** From the map: open a Crux's questions in the drawer. */
  const openCrux = (routeId: string, cruxId: string) => {
    routeList.select(routeId);
    setActiveCruxId(cruxId);
    setPanelOpen(true);
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
        addMode={addMode}
        isDrawing={isDrawing}
        draft={draft}
        onDraftChange={setDraft}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        startPoint={startPoint}
        endPoint={endPoint}
        onStartPointChange={setStartPoint}
        onEndPointChange={setEndPoint}
        // The Route being edited is the draft for now; its old line and
        // Cruxes would only sit under it.
        routes={
          editing && addMode === "draw" ? routes.filter((r) => r.id !== editing.id) : routes
        }
        selectedId={selectedId}
        onSelectRoute={routeList.select}
        focus={focus}
        onDropFiles={upload}
        corridor={corridor}
        showCorridor={showCorridor}
        corridorOpacity={corridorOpacity}
        onCruxClick={openCrux}
        placeCruxOn={placingCrux && selected && !pendingCrux ? selected.line : null}
        pendingCrux={pendingCrux?.position ?? null}
        onPlaceCrux={setPendingCrux}
        onCancelPlaceCrux={stopPlacingCrux}
      />

      <RoutePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        panelWidth={panelWidth}
        onPanelWidthChange={setPanelWidth}
        onResetPanelWidth={resetWidth}
        addMode={addMode}
        onAddModeChange={changeAddMode}
        startPoint={startPoint}
        endPoint={endPoint}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        onClearStart={() => setStartPoint(null)}
        onClearEnd={() => setEndPoint(null)}
        onGenerate={generate}
        isRouting={isRouting}
        backendReady={backendReady}
        isDrawing={isDrawing}
        onStartDrawing={() => setIsDrawing(true)}
        draft={draft}
        editingName={editing?.name ?? null}
        onUndoDraft={() => setDraft((prev) => prev.slice(0, -1))}
        onClearDraft={() => setDraft([])}
        onFinishDraft={finishDraft}
        onCancelDraw={stopDrawing}
        routes={routes}
        selectedId={selectedId}
        onSelectRoute={routeList.select}
        onToggleRoute={routeList.toggleVisible}
        onDeleteRoute={routeList.remove}
        onEditRoute={editRoute}
        onUpload={upload}
        isIdentifying={isIdentifying}
        onIdentify={identify}
        activeCruxId={activeCruxId}
        onActivateCrux={activateCrux}
        onAnswer={routeList.setAnswer}
        onRestoreCrux={routeList.restoreCrux}
        onRemoveCrux={routeList.removeCrux}
        placingCrux={placingCrux && selected !== null}
        onPlaceCrux={togglePlacingCrux}
        showCorridor={showCorridor}
        onShowCorridorChange={setShowCorridor}
        corridorOpacity={corridorOpacity}
        onCorridorOpacityChange={setCorridorOpacity}
      />

      <AddCruxDialog
        open={pendingCrux !== null}
        defaults={defaultsAt(selected?.crux?.segments, pendingCrux?.distance_m ?? 0)}
        onCancel={stopPlacingCrux}
        onAdd={(input) => pendingCrux && addCrux({ ...input, ...pendingCrux })}
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
          <Typography>Routing in progress...</Typography>
        </Box>
      </Backdrop>
    </div>
  );
};

export default App;
