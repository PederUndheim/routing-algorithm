import { useState } from "react";
import { useMapEvents } from "react-leaflet";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const CursorCoords = () => {
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(null);

  useMapEvents({
    mousemove(e) {
      setPos({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
    mouseout() {
      setPos(null);
    },
  });

  return (
    <Box
      sx={{
        position: "fixed",
        right: 5,
        bottom: 22,
        zIndex: 1200,
        pointerEvents: "none",
        backgroundColor: "#555555",
        color: "white",
        px: 1,
        py: 0.5,
        borderRadius: 1.5,
        boxShadow: "0 8px 20px rgba(0,0,0,0.25)",
        opacity: pos ? 1 : 0.7,
      }}
    >
      <Typography sx={{ fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
        {pos
          ? `${pos.lat.toFixed(3)}°N, ${pos.lng.toFixed(3)}°E`
          : "Move cursor to see coordinates"}
      </Typography>
    </Box>
  );
};

export default CursorCoords;
