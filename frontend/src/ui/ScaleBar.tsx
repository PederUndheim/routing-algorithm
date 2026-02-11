import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";

type ScaleBarProps = {
  position?: L.ControlPosition;
};

const ScaleBar = ({ position = "bottomleft" }: ScaleBarProps) => {
  const map = useMap();

  useEffect(() => {
    if (!map) return;

    const control = L.control.scale({
      position: "bottomleft",
      metric: true,
      imperial: false,
      maxWidth: 180,
      updateWhenIdle: true,
    });
    control.addTo(map);
    return () => {
      control.remove();
    };
  }, [map, position]);

  return null;
};

export default ScaleBar;
