import { useRef, useState, useEffect } from "react";

import type { FeatureCollection } from "geojson";
import type { BasemapId } from "./layers/basemaps";
import type { MapApi } from "./map/MapView";
import type { OverlayId } from "./layers/overlays";
import type { LatLng, PickMode, UserGeoJsonLayer } from "./types/mapTypes";
import type { CorridorBounds, CorridorMode, CorridorVariantUrls } from "./types/corridor";

import MapView from "./map/MapView";
import Sidebar from "./routing/Sidebar";

import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";
import Backdrop from "@mui/material/Backdrop";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

const formatApiErrorDetail = (detail: unknown): string => {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0];
    if (first && typeof first === "object") {
      const item = first as { msg?: unknown; loc?: unknown[] };
      const msg = typeof item.msg === "string" ? item.msg : null;
      const loc = Array.isArray(item.loc) ? item.loc.join(".") : null;
      if (msg && loc) return `${loc}: ${msg}`;
      if (msg) return msg;
    }
    return "Request validation failed.";
  }
  if (detail && typeof detail === "object") {
    const maybeMessage = (detail as { message?: unknown }).message;
    if (typeof maybeMessage === "string") return maybeMessage;
  }
  return "Failed to generate route.";
};

const App = () => {
  const [basemap, setBasemap] = useState<BasemapId>("topo");
  const [overlays, setOverlays] = useState<Record<OverlayId, boolean>>({
    study_areas: false,
    slope: false,
    slope_runout: false,
  });
  const [overlayOpacity, setOverlayOpacity] = useState<
    Record<OverlayId, number>
  >({
    study_areas: 1.0,
    slope: 0.55,
    slope_runout: 0.38,
  });
  const [userGeoJsonLayers, setUserGeoJsonLayers] = useState<
    UserGeoJsonLayer[]
  >([]);
  const [geoJsonVisible, setGeoJsonVisible] = useState<boolean>(true);

  const [sidebarOpen, setsidebarOpen] = useState(false);

  const [startPoint, setStartPoint] = useState<LatLng | null>(null);
  const [endPoint, setEndPoint] = useState<LatLng | null>(null);
  const [pickMode, setPickMode] = useState<PickMode>(null);

  const mapApiRef = useRef<MapApi | null>(null);

  const [isRouting, setIsRouting] = useState(false);
  const [routeGeoJson, setRouteGeoJson] = useState<FeatureCollection | null>(
    null
  );
  const [showCorridor, setShowCorridor] = useState(false);
  const [corridorMode, setCorridorMode] = useState<CorridorMode>("balanced");
  const [corridorPngUrl, setCorridorPngUrl] = useState<string | null>(null);
  const [corridorPngUrls, setCorridorPngUrls] = useState<CorridorVariantUrls>({});
  const [corridorBounds, setCorridorBounds] = useState<CorridorBounds | null>(
    null
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [gpxDownloadUrl, setGpxDownloadUrl] = useState<string | null>(null);
  const [geojsonDownloadUrl, setGeojsonDownloadUrl] = useState<string | null>(
    null
  );

  useEffect(() => {
    const API = import.meta.env.VITE_API_BASE_URL;

    if (!API) return;

    let cancelled = false;

    const warmUp = async () => {
      try {
        await fetch(`${API}/health`, {
          method: "GET",
          cache: "no-store",
        });
      } catch (err) {
        if (!cancelled) {
          console.debug("Backend warm-up ping failed (likely cold start)");
        }
      }
    };
    warmUp();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleGenerateRoute = async ({
    lambdaWeight,
    smoothThreshold,
    avoidLake,
    avoidGlacier,
    trackInfluenceMode,
    corridorMode,
  }: {
    lambdaWeight: number;
    smoothThreshold: number;
    avoidLake: boolean;
    avoidGlacier: boolean;
    trackInfluenceMode: "off" | "forest_only" | "balanced" | "strong";
    corridorMode: CorridorMode;
  }) => {
    if (!startPoint || !endPoint) return;

    if (activeRunId) {
      await deleteRun(activeRunId);
      setActiveRunId(null);
    }

    const runId = crypto.randomUUID().replaceAll("-", "_");
    setRouteGeoJson(null);
    setCorridorPngUrl(null);
    setCorridorPngUrls({});
    setGpxDownloadUrl(null);
    setGeojsonDownloadUrl(null);
    setIsRouting(true);
    setErrorMsg(null);

    try {
      const API = import.meta.env.VITE_API_BASE_URL;

      const res = await fetch(`${API}/route`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: "run_" + runId,
          start: startPoint,
          end: endPoint,
          lambda_weight: lambdaWeight,
          smooth_threshold: smoothThreshold,
          avoid_lake: avoidLake,
          avoid_glacier: avoidGlacier,
          track_influence_mode: trackInfluenceMode,
          corridor_mode: corridorMode,
        }),
      });

      if (!res.ok) {
        let msg = "Failed to generate route.";
        try {
          const err = await res.json();
          msg = formatApiErrorDetail(err?.detail);
        } catch {
          msg = await res.text();
        }
        setErrorMsg(msg);
        return;
      }

      const data = await res.json();
      setRouteGeoJson(data.route);
      setCorridorPngUrls((data.corridor?.png_urls ?? {}) as CorridorVariantUrls);
      setCorridorPngUrl((data.corridor?.png_urls?.[corridorMode] ?? data.corridor?.png_url) ?? null);
      setCorridorBounds(data.corridor?.bounds ?? null);
      setActiveRunId(data.run_id ?? null);
      setGpxDownloadUrl(data.downloads?.gpx_url ?? null);
      setGeojsonDownloadUrl(data.downloads?.geojson_url ?? null);
    } finally {
      setIsRouting(false);
    }
  };

  const clearStart = () => {
    setStartPoint(null);
    setRouteGeoJson(null);
    setCorridorPngUrl(null);
    setCorridorPngUrls({});
    setCorridorBounds(null);
    setGpxDownloadUrl(null);
    setGeojsonDownloadUrl(null);
  };

  const clearEnd = () => {
    setEndPoint(null);
    setRouteGeoJson(null);
    setCorridorPngUrl(null);
    setCorridorPngUrls({});
    setCorridorBounds(null);
    setGpxDownloadUrl(null);
    setGeojsonDownloadUrl(null);
  };

  const toggleGeoJsonLayer = (id: string) => {
    setUserGeoJsonLayers((prev) =>
      prev.map((layer) =>
        layer.id === id ? { ...layer, visible: !layer.visible } : layer
      )
    );
  };
  const removeGeoJsonLayer = (id: string) => {
    setUserGeoJsonLayers((prev) => prev.filter((layer) => layer.id !== id));
  };

  const deleteRun = async (runId: string) => {
    const API = import.meta.env.VITE_API_BASE_URL;
    await fetch(`${API}/runs_output/${runId}`, { method: "DELETE" });
  };

  useEffect(() => {
    if (!startPoint || !endPoint) {
      setRouteGeoJson(null);
      setCorridorPngUrl(null);
      setCorridorPngUrls({});
      setCorridorBounds(null);
      setGpxDownloadUrl(null);
      setGeojsonDownloadUrl(null);
    }
  }, [startPoint, endPoint]);

  useEffect(() => {
    setCorridorPngUrl(corridorPngUrls[corridorMode] ?? null);
  }, [corridorMode, corridorPngUrls]);

  const addGeoJsonLayer = (name: string, data: FeatureCollection) => {
    setUserGeoJsonLayers((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        name,
        visible: true,
        data,
      },
    ]);
  };

  return (
    <div style={{ height: "100dvh" }}>
      <MapView
        basemap={basemap}
        onBasemapChange={setBasemap}
        overlays={overlays}
        onToggleOverlay={(id) =>
          setOverlays((prev) => ({ ...prev, [id]: !prev[id] }))
        }
        overlayOpacity={overlayOpacity}
        onOverlayOpacityChange={(id, opacity) =>
          setOverlayOpacity((prev) => ({ ...prev, [id]: opacity }))
        }
        onMapReady={(api) => {
          mapApiRef.current = api;
        }}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setsidebarOpen((v) => !v)}
        onCloseSidebar={() => setsidebarOpen(false)}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        startPoint={startPoint}
        endPoint={endPoint}
        onStartPointChange={setStartPoint}
        onEndPointChange={setEndPoint}
        routeGeoJson={routeGeoJson}
        showCorridor={showCorridor}
        corridorPngUrl={corridorPngUrl}
        corridorBounds={corridorBounds}
        userGeoJsonLayers={userGeoJsonLayers}
        onAddGeoJson={addGeoJsonLayer}
        onToggleGeoJson={toggleGeoJsonLayer}
        onRemoveGeoJson={removeGeoJsonLayer}
        geoJsonVisible={geoJsonVisible}
        onToggleGeoJsonVisible={() => setGeoJsonVisible((visible) => !visible)}
      />

      <Sidebar
        open={sidebarOpen}
        onClose={() => setsidebarOpen(false)}
        startPoint={startPoint}
        endPoint={endPoint}
        pickMode={pickMode}
        onPickModeChange={setPickMode}
        showCorridor={showCorridor}
        onShowCorridorChange={setShowCorridor}
        corridorMode={corridorMode}
        onCorridorModeChange={setCorridorMode}
        onClearStart={clearStart}
        onClearEnd={clearEnd}
        onGenerate={handleGenerateRoute}
        runId={activeRunId}
        gpxDownloadUrl={gpxDownloadUrl}
        geojsonDownloadUrl={geojsonDownloadUrl}
      />

      <Snackbar
        open={Boolean(errorMsg)}
        autoHideDuration={6000}
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
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
          }}
        >
          <CircularProgress />
          <Typography>
            Routing in progress. This may take some seconds.
          </Typography>
        </Box>
      </Backdrop>
    </div>
  );
};

export default App;
