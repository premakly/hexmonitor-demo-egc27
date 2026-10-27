// Base maps: raster tiles that need no key.
//
// Every one of them is declared in the map's style from the start and only
// their visibility changes. Swapping the whole style instead would wipe the
// data layers drawn on top and force them to be rebuilt on each change.
//
// `tone` says whether the picture is dark or light, because what is drawn on
// top has to contrast with it: pale hexagons on a dark map, dark ones on a
// light map.

export const BASEMAPS = [
  {
    id: 'carto-dark',
    label: 'Dark',
    provider: 'CARTO',
    tone: 'dark',
    tiles: ['a', 'b', 'c', 'd'].map(s => `https://${s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png`),
    maxzoom: 20,
    attribution: '© OpenStreetMap contributors © CARTO'
  },
  {
    id: 'carto-light',
    label: 'Light',
    provider: 'CARTO',
    tone: 'light',
    tiles: ['a', 'b', 'c', 'd'].map(s => `https://${s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`),
    maxzoom: 20,
    attribution: '© OpenStreetMap contributors © CARTO'
  },
  {
    id: 'esri-satellite',
    label: 'Satellite',
    provider: 'Esri',
    tone: 'dark',
    tiles: ['https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 19,
    attribution: '© Esri, Maxar, Earthstar Geographics, and the GIS User Community'
  },
  {
    id: 'osm',
    label: 'OpenStreetMap',
    provider: 'OpenStreetMap',
    tone: 'light',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    maxzoom: 19,
    attribution: '© OpenStreetMap contributors'
  }
]

export const DEFAULT_BASEMAP = 'carto-dark'

export function basemapById(id) {
  return BASEMAPS.find(b => b.id === id) || BASEMAPS.find(b => b.id === DEFAULT_BASEMAP)
}

const sourceId = id => `basemap-${id}`
export const layerId = id => `basemap-${id}-layer`

// The map's style: one raster source and layer per base map, only the chosen
// one visible. raster-saturation -1 turns a picture greyscale, which is how
// satellite and OpenStreetMap are brought into the interface's palette.
export function buildStyle(basemapId, grayscale = true) {
  const chosen = basemapById(basemapId).id
  const sources = {}
  const layers = []

  for (const b of BASEMAPS) {
    sources[sourceId(b.id)] = {
      type: 'raster',
      tiles: b.tiles,
      tileSize: 256,
      maxzoom: b.maxzoom,
      attribution: b.attribution
    }
    layers.push({
      id: layerId(b.id),
      type: 'raster',
      source: sourceId(b.id),
      layout: { visibility: b.id === chosen ? 'visible' : 'none' },
      paint: { 'raster-saturation': grayscale ? -1 : 0 }
    })
  }

  return { version: 8, sources, layers }
}

// Switch an existing map to another base map without touching its data layers.
export function applyBasemap(map, basemapId, grayscale = true) {
  const chosen = basemapById(basemapId).id
  for (const b of BASEMAPS) {
    map.setLayoutProperty(layerId(b.id), 'visibility', b.id === chosen ? 'visible' : 'none')
    map.setPaintProperty(layerId(b.id), 'raster-saturation', grayscale ? -1 : 0)
  }
}

// Colours for what is drawn over the base map.
//
// The interface is grey; colour is kept for the one thing that is a finding
// rather than a backdrop: where a vessel probably went while it was silent.
export const ACCENT = '#f5a524'

const INK = {
  dark: { hex: '#e5e7eb', outline: '#e5e7eb', track: '#f3f4f6', circle: '#f3f4f6', haloOpacity: 0.55 },
  light: { hex: '#1f2937', outline: '#1f2937', track: '#111827', circle: '#111827', haloOpacity: 0.55 }
}

export function inkFor(basemapId) {
  return INK[basemapById(basemapId).tone]
}
