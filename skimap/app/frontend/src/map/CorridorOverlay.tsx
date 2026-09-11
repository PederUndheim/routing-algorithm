import { ImageOverlay } from "react-leaflet";

import { apiUrl } from "../api";
import type { Corridor } from "../types";

/** The corridor, drawn under the route it belongs to.
 *
 * Just a picture between two corners: the backend has already warped it to
 * Web Mercator, which is the projection Leaflet stretches an image overlay
 * in, so the bounds are the warped raster's own edges and nothing here has
 * to know about the 25833 grid it came from.
 *
 * `opacity` multiplies whatever blue.lyrx already said. Its class breaks
 * carry their own alpha - transparent below a score of 0.05, solid above
 * 0.15 - so the shape of the fade is the style's and this only decides how
 * much of the map shows through the whole band. At 1 it is exactly the
 * ArcGIS rendering.
 */
const CorridorOverlay = ({ corridor, opacity = 0.5 }: {
  corridor: Corridor;
  opacity?: number;
}) => {
  const { west, south, east, north } = corridor.bounds;

  return (
    <ImageOverlay
      url={apiUrl(corridor.png_path)}
      bounds={[
        [south, west],
        [north, east],
      ]}
      opacity={opacity}
      interactive={false}
      pane="corridor"
    />
  );
};

export default CorridorOverlay;
