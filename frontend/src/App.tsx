import { useRef, useState, useEffect } from "react";

import type { FeatureCollection } from "geojson";
import type { BasemapId } from "./layers/basemaps";
import type { MapApi } from "./map/MapView";
import type { OverlayId } from "./layers/overlays";
import type { LatLng, PickMode, UserGeoJsonLayer } from "./types/mapTypes";
import type { CorridorBounds } from "./types/corridor";

import MapView from "./map/MapView";
import Sidebar from "./routing/Sidebar";

import Snackbar from "@mui/material/Snackbar";
import Alert from "@mui/material/Alert";
import Backdrop from "@mui/material/Backdrop";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

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
  const [corridorPngUrl, setCorridorPngUrl] = useState<string | null>(null);
  const [corridorBounds, setCorridorBounds] = useState<CorridorBounds | null>(
    null
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleGenerateRoute = async ({
    lambdaWeight,
    smoothThreshold,
  }: {
    lambdaWeight: number;
    smoothThreshold: number;
  }) => {
    if (!startPoint || !endPoint) return;

    const runId = crypto.randomUUID().replaceAll("-", "_");
    setRouteGeoJson(null);
    setCorridorPngUrl(null);
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
          start: startPoint,
          end: endPoint,
          lambda_weight: lambdaWeight,
          smooth_threshold: smoothThreshold,
          name: "run_" + runId,
        }),
      });

      if (!res.ok) {
        let msg = "Failed to generate route.";
        try {
          const err = await res.json();
          msg = err?.detail ?? msg;
        } catch {
          msg = await res.text();
        }
        setErrorMsg(msg);
        return;
      }

      const data = await res.json();
      setRouteGeoJson(data.route);
      setCorridorPngUrl(data.corridor?.png_url ?? null);
      setCorridorBounds(data.corridor?.bounds ?? null);
    } finally {
      setIsRouting(false);
    }
  };

  const clearStart = () => {
    setStartPoint(null);
    setRouteGeoJson(null);
    setCorridorPngUrl(null);
    setCorridorBounds(null);
  };

  const clearEnd = () => {
    setEndPoint(null);
    setRouteGeoJson(null);
    setCorridorPngUrl(null);
    setCorridorBounds(null);
  };

  useEffect(() => {
    if (!startPoint || !endPoint) {
      setRouteGeoJson(null);
      setCorridorPngUrl(null);
      setCorridorBounds(null);
    }
  }, [startPoint, endPoint]);

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

  return (
    <div style={{ height: "100vh" }}>
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
        onClearStart={clearStart}
        onClearEnd={clearEnd}
        onGenerate={handleGenerateRoute}
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
