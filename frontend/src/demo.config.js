// What a visitor sees on arriving at the demo.
export const DEMO_DEFAULTS = {
  // Base map at each arrival (one of lib/basemaps.js: carto-dark, carto-light,
  // esri-satellite, osm). A visitor can change it; it is not remembered.
  basemap: 'esri-satellite',
  grayscale: true,

  // The trajectory opened at arrival: a vessel (MMSI) and the gap size, in
  // cells; size null opens the smallest size. If the vessel has no gap of
  // that size, the first gap of the list is opened instead.
  vessel: 538009058,
  size: 8
}
