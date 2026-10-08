import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import Alert from "@mui/material/Alert";
import Backdrop from "@mui/material/Backdrop";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import Typography from "@mui/material/Typography";

import { checkHealth, requestCrux, requestRoute } from "./api";
import { defaultsAt, problemOf } from "./crux/assessment";
import { cruxTitle } from "./dangerClasses";
import { DEFAULT_BASEMAP } from "./layers/basemaps";
import type { BasemapId } from "./layers/basemaps";
import { DEFAULT_OPACITY, DEFAULT_OVERLAYS } from "./layers/overlays";
import type { OverlayId } from "./layers/overlays";
import MapView from "./map/MapView";
import { createRouteList, geodesicLength, isEdited } from "./routes/routeList";
import type { CruxMarker } from "./routes/routeList";
import { MARKER_LEAD_M, pointAtDistance, sliceLine } from "./routes/snap";
import AddCruxDialog, { EditCruxDialog, problemColor } from "./routing/AddCruxDialog";
import type { StretchPreview } from "./routing/AddCruxDialog";
import ConfirmDialog from "./routing/ConfirmDialog";
import RoutePanel from "./routing/RoutePanel";
import { usePanelWidth } from "./routing/usePanelWidth";
import { dangerColor } from "./theme";
import type { AddMode, CruxEntry, Extent, LatLng, MapFocus, PickMode } from "./types";

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
  // What the open Add crux form would colour, drawn on the map as it is set.
  const [stretchPreview, setStretchPreview] = useState<StretchPreview | null>(null);
  // A Crux picked up with Move: the next map click puts it down on the
  // Selected route.
  const [movingCruxId, setMovingCruxId] = useState<string | null>(null);
  // A Crux whose extent is being dragged about on the map, and its extent
  // and marker before, to go back to if the edit is given up.
  const [extentEdit, setExtentEdit] = useState<{
    routeId: string;
    cruxId: string;
    before: Extent | undefined;
    marker: CruxMarker;
  } | null>(null);
  // Identify cruxes pressed on a Route whose identified Cruxes the user has
  // already worked on: it waits for them to say the work may go.
  const [confirmIdentify, setConfirmIdentify] = useState(false);
  // A Crux whose name, symbol and colour are open in the Edit crux form.
  const [editingCrux, setEditingCrux] = useState<{ routeId: string; cruxId: string } | null>(
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
  const runIdentify = async () => {
    setConfirmIdentify(false);
    if (!selected) return;
    const { id, line } = selected;
    if (extentEdit?.routeId === id) cancelExtentEdit();

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

  /** Identifying again replaces the identified Cruxes, and with them all the
   *  user has made of them - so where there is any, ask first. */
  const identify = () => {
    if (selected?.cruxes.some(isEdited)) setConfirmIdentify(true);
    else void runIdentify();
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
    setMovingCruxId(null);
  }, []);

  const editedRoute = extentEdit ? (routes.find((r) => r.id === extentEdit.routeId) ?? null) : null;
  const editedCrux = editedRoute?.cruxes.find((c) => c.id === extentEdit?.cruxId) ?? null;

  /** Give up an extent edit: the Crux goes back to what it had, marker too. */
  const cancelExtentEdit = useCallback(() => {
    if (extentEdit) {
      routeList.setExtent(extentEdit.routeId, extentEdit.cruxId, extentEdit.before);
      routeList.setMarker(extentEdit.routeId, extentEdit.cruxId, extentEdit.marker);
    }
    setExtentEdit(null);
  }, [extentEdit]);

  /** Set the extent being edited, and take the marker along to stand
   *  `MARKER_LEAD_M` before its start - where an identified Crux's marker
   *  would be. It can still be moved on its own afterwards. */
  const applyExtent = (extent: Extent) => {
    if (!extentEdit || !editedRoute) return;
    const { routeId, cruxId } = extentEdit;
    const distance_m = Math.max(extent.start_m - MARKER_LEAD_M, 0);
    routeList.setExtent(routeId, cruxId, extent);
    routeList.moveCrux(routeId, cruxId, {
      position: pointAtDistance(editedRoute.line, distance_m),
      distance_m,
    });
  };

  /** Keep an extent edit. An identified Crux dragged back onto its own area
   *  is simply its area again, not an edit. */
  const finishExtentEdit = () => {
    if (editedRoute && editedCrux?.extent && editedCrux.area) {
      const { extent, area } = editedCrux;
      const same =
        Math.abs(extent.start_m - area.start_m) < 0.5 && Math.abs(extent.end_m - area.end_m) < 0.5;
      if (same) routeList.setExtent(editedRoute.id, editedCrux.id, undefined);
    }
    setExtentEdit(null);
  };

  /** Back to the start: an identified Crux's area as the analysis found it,
   *  still being edited; a hand-placed Crux's marker alone, edit done. */
  const resetExtentEdit = () => {
    if (!editedRoute || !editedCrux) return;
    if (editedCrux.area) {
      applyExtent(editedCrux.area);
    } else {
      routeList.setExtent(editedRoute.id, editedCrux.id, undefined);
      if (extentEdit) routeList.setMarker(editedRoute.id, editedCrux.id, extentEdit.marker);
      setExtentEdit(null);
    }
  };

  /** Put handles on the ends of what a Crux colours: its edited extent, its
   *  analysed area, or - for one placed by hand with none - a short stretch
   *  ahead of its marker to pull out from. */
  const startExtentEdit = (routeId: string, crux: CruxEntry) => {
    const route = routes.find((r) => r.id === routeId);
    if (!route) return;
    stopPlacingCrux();
    if (extentEdit) cancelExtentEdit();
    setPickMode(null);
    const length = geodesicLength(route.line.coordinates);
    const start =
      crux.extent ??
      crux.area ?? {
        start_m: Math.min(crux.distance_m, Math.max(length - 50, 0)),
        end_m: Math.min(crux.distance_m + 50, length),
      };
    setExtentEdit({
      routeId,
      cruxId: crux.id,
      before: crux.extent,
      marker: { position: crux.position, distance_m: crux.distance_m, moved: crux.moved },
    });
    routeList.setExtent(routeId, crux.id, start);
    setActiveCruxId(null);
  };

  const togglePlacingCrux = () => {
    if (extentEdit) {
      cancelExtentEdit();
      return;
    }
    if (placingCrux || movingCruxId) {
      stopPlacingCrux();
      return;
    }
    setPickMode(null);
    setPlacingCrux(true);
  };

  const startMovingCrux = (crux: CruxEntry) => {
    stopPlacingCrux();
    if (extentEdit) finishExtentEdit();
    setPickMode(null);
    setMovingCruxId(crux.id);
    setActiveCruxId(null);
  };

  /** The map click while placing or moving: a Crux in hand goes down there,
   *  else the spot waits in the Add crux form. */
  const placeCrux = (spot: { position: LatLng; distance_m: number }) => {
    if (movingCruxId && selected) {
      routeList.moveCrux(selected.id, movingCruxId, spot);
      setMovingCruxId(null);
    } else {
      setPendingCrux(spot);
    }
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

  // The Crux open in the Edit crux form, if it is still there.
  const cruxInForm = editingCrux
    ? (routes
        .find((r) => r.id === editingCrux.routeId)
        ?.cruxes.find((c) => c.id === editingCrux.cruxId) ?? null)
    : null;

  const pendingStretch = useMemo(() => {
    if (!selected || !pendingCrux || !stretchPreview || stretchPreview.length_m <= 0) return null;
    const { distance_m } = pendingCrux;
    const positions = sliceLine(selected.line, distance_m, distance_m + stretchPreview.length_m).map(
      ([lng, lat]) => [lat, lng] as [number, number]
    );
    return { positions, color: stretchPreview.color };
  }, [selected, pendingCrux, stretchPreview]);

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
        placeCruxOn={
          selected && !pendingCrux && (placingCrux || movingCruxId) ? selected.line : null
        }
        pendingCrux={pendingCrux?.position ?? null}
        pendingStretch={pendingStretch}
        onPlaceCrux={placeCrux}
        onCancelPlaceCrux={stopPlacingCrux}
        extentEdit={
          editedRoute && editedCrux?.extent
            ? { line: editedRoute.line, extent: editedCrux.extent, color: dangerColor(editedCrux) }
            : null
        }
        onExtentChange={applyExtent}
        onCancelExtent={cancelExtentEdit}
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
        // Whatever is being done to a Crux, it is marked in the list - folded,
        // so the list stays short while the map or a form is in use.
        highlightedCruxId={extentEdit?.cruxId ?? movingCruxId ?? editingCrux?.cruxId ?? null}
        onActivateCrux={activateCrux}
        onAnswer={routeList.setAnswer}
        onOverall={routeList.setOverall}
        onKeep={routeList.setKeep}
        onRestoreCrux={routeList.restoreCrux}
        onDeleteCrux={routeList.deleteCrux}
        onUndeleteCrux={routeList.undeleteCrux}
        onEditCrux={(routeId, crux) => {
          setEditingCrux({ routeId, cruxId: crux.id });
          setActiveCruxId(null);
        }}
        onMoveCrux={(_routeId, crux) => startMovingCrux(crux)}
        onEditExtent={startExtentEdit}
        placingCrux={
          (placingCrux || movingCruxId !== null || extentEdit !== null) && selected !== null
        }
        placingText={
          extentEdit
            ? "Drag the two handles along the route to where the crux starts and ends."
            : movingCruxId
              ? "Click on the map - the marker moves to the nearest point of the route."
              : "Click on the map - the crux goes on the nearest point of the route."
        }
        onPlaceCrux={togglePlacingCrux}
        editingExtent={extentEdit !== null}
        onFinishExtent={finishExtentEdit}
        onResetExtent={resetExtentEdit}
        showCorridor={showCorridor}
        onShowCorridorChange={setShowCorridor}
        corridorOpacity={corridorOpacity}
        onCorridorOpacityChange={setCorridorOpacity}
      />

      <ConfirmDialog
        open={confirmIdentify}
        title="Identify cruxes again?"
        confirmLabel="Identify again"
        onCancel={() => setConfirmIdentify(false)}
        onConfirm={() => void runIdentify()}
      >
        The identified cruxes on this route will be replaced by a fresh analysis, and everything
        you have done with them goes too: ratings, overall assessments, keep choices, moved
        markers, edited extents and deletions. Cruxes you added by hand are kept as they are.
      </ConfirmDialog>

      <EditCruxDialog
        initial={
          cruxInForm
            ? {
                description: cruxTitle(cruxInForm),
                problem: problemOf(cruxInForm),
                color: dangerColor(cruxInForm),
              }
            : null
        }
        colorChosen={
          cruxInForm ? dangerColor(cruxInForm) !== problemColor(problemOf(cruxInForm)) : false
        }
        onCancel={() => setEditingCrux(null)}
        onSave={(details) => {
          if (editingCrux) routeList.editCrux(editingCrux.routeId, editingCrux.cruxId, details);
          setEditingCrux(null);
        }}
      />

      <AddCruxDialog
        open={pendingCrux !== null}
        defaults={defaultsAt(selected?.crux?.segments, pendingCrux?.distance_m ?? 0)}
        maxLength={Math.max((selected?.lengthM ?? 0) - (pendingCrux?.distance_m ?? 0), 0)}
        onPreview={setStretchPreview}
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
