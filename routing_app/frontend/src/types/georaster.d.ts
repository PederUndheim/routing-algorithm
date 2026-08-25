declare module "georaster" {
  const parseGeoraster: (data: ArrayBuffer) => Promise<any>;
  export default parseGeoraster;
}

declare module "georaster-layer-for-leaflet" {
  import * as L from "leaflet";

  export default class GeoRasterLayer extends L.GridLayer {
    constructor(options: any);
    getBounds(): L.LatLngBounds;
  }
}
