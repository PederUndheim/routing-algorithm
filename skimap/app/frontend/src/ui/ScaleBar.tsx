import { useEffect } from "react";
import { useMap } from "react-leaflet";
import { control } from "leaflet";
import type { ControlPosition } from "leaflet";

const ScaleBar = ({ position = "bottomleft" }: { position?: ControlPosition }) => {
  const map = useMap();

  useEffect(() => {
    const scale = control.scale({
      position,
      metric: true,
      imperial: false,
      maxWidth: 180,
      updateWhenIdle: true,
    });
    scale.addTo(map);
    return () => {
      scale.remove();
    };
  }, [map, position]);

  return null;
};

export default ScaleBar;
