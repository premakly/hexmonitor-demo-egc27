<template>
  <div ref="container" class="experiment-map"></div>
</template>

<script setup>
// The Experiment view's own map. Kept apart from MapView on purpose: it draws
// several completions of one gap side by side, which MapView's layers (one
// vessel's track and its scenarios) were never meant to carry.
import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { ref } from 'vue'

import { applyBasemap, buildStyle, inkFor } from '../lib/basemaps.js'
import { emptyCollection } from '../lib/geo.js'

const props = defineProps({
  basemap: { type: String, required: true },
  grayscale: { type: Boolean, default: true },
  layers: { type: Object, default: null }, // { grid, context, truth, methods, cells, highlight }
  fit: { type: Object, default: null } // { bounds, token }
})

const container = ref(null)
let map = null
let ready = false
let appliedFitToken = null

const byKind = kind => ['==', ['get', 'kind'], kind]

function build() {
  const ink = inkFor(props.basemap)

  // The H3 grid around the gap, very faint and fading outward: it shows the
  // cells the methods move through without competing with them.
  map.addSource('exp-grid', { type: 'geojson', data: emptyCollection() })
  map.addLayer({
    id: 'exp-grid-line',
    type: 'line',
    source: 'exp-grid',
    paint: { 'line-color': ink.hex, 'line-width': 0.8, 'line-opacity': ['*', 0.3, ['get', 'fade']] }
  })

  map.addSource('exp-cells', { type: 'geojson', data: emptyCollection() })
  map.addLayer({
    id: 'exp-cells-fill',
    type: 'fill',
    source: 'exp-cells',
    // Light fills, so the cells of several methods stay readable where they
    // overlap; each method's own outline tells them apart.
    paint: {
      'fill-color': ['get', 'colour'],
      'fill-opacity': ['match', ['get', 'rank'], 0, 0.18, 0.06]
    }
  })
  map.addLayer({
    id: 'exp-cells-outline',
    type: 'line',
    source: 'exp-cells',
    paint: {
      'line-color': ['get', 'colour'],
      'line-width': ['match', ['get', 'rank'], 0, 1.4, 0.6],
      'line-opacity': ['match', ['get', 'rank'], 0, 0.9, 0.4]
    }
  })

  // What Hexa's reasoning panel points at: a picked branch (dashed cells and
  // its line) and the cell of a hovered step (bright outline).
  map.addSource('exp-highlight', { type: 'geojson', data: emptyCollection() })
  map.addLayer({
    id: 'exp-highlight-branch', type: 'line', source: 'exp-highlight', filter: byKind('branch'),
    paint: { 'line-color': ink.track, 'line-width': 1.2, 'line-dasharray': [2, 2], 'line-opacity': 0.8 }
  })
  map.addLayer({
    id: 'exp-highlight-branch-line', type: 'line', source: 'exp-highlight', filter: byKind('branch-line'),
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ink.track, 'line-width': 2, 'line-opacity': 0.9 }
  })
  map.addLayer({
    id: 'exp-highlight-cell', type: 'line', source: 'exp-highlight', filter: byKind('cell'),
    paint: { 'line-color': ink.track, 'line-width': 3 }
  })

  map.addSource('exp-context', { type: 'geojson', data: emptyCollection() })
  map.addLayer({
    id: 'exp-context-line', type: 'line', source: 'exp-context', filter: byKind('line'),
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ink.track, 'line-width': 1.2, 'line-opacity': 0.5 }
  })
  map.addLayer({
    id: 'exp-context-points', type: 'circle', source: 'exp-context', filter: byKind('point'),
    paint: { 'circle-radius': 2, 'circle-color': ink.track, 'circle-opacity': 0.5 }
  })

  // The ground truth through the gap: what every method is measured against.
  map.addSource('exp-truth', { type: 'geojson', data: emptyCollection() })
  map.addLayer({
    id: 'exp-truth-line', type: 'line', source: 'exp-truth', filter: byKind('line'),
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ink.track, 'line-width': 3, 'line-dasharray': [1, 1.2] }
  })
  map.addLayer({
    id: 'exp-truth-points', type: 'circle', source: 'exp-truth', filter: byKind('point'),
    paint: { 'circle-radius': 4, 'circle-color': ink.track, 'circle-stroke-color': '#0a0b0d', 'circle-stroke-width': 1 }
  })

  map.addSource('exp-methods', { type: 'geojson', data: emptyCollection() })
  map.addLayer({
    id: 'exp-methods-line', type: 'line', source: 'exp-methods', filter: byKind('line'),
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'colour'], 'line-width': 2.5, 'line-opacity': 0.9 }
  })
  map.addLayer({
    id: 'exp-methods-points', type: 'circle', source: 'exp-methods', filter: byKind('point'),
    paint: { 'circle-radius': 3, 'circle-color': ['get', 'colour'], 'circle-stroke-color': '#0a0b0d', 'circle-stroke-width': 1 }
  })
}

function applyInk() {
  const ink = inkFor(props.basemap)
  map.setPaintProperty('exp-grid-line', 'line-color', ink.hex)
  for (const id of ['exp-highlight-branch', 'exp-highlight-branch-line', 'exp-highlight-cell']) {
    map.setPaintProperty(id, 'line-color', ink.track)
  }
  map.setPaintProperty('exp-context-line', 'line-color', ink.track)
  map.setPaintProperty('exp-context-points', 'circle-color', ink.track)
  map.setPaintProperty('exp-truth-line', 'line-color', ink.track)
  map.setPaintProperty('exp-truth-points', 'circle-color', ink.track)
}

function refreshData() {
  if (!ready) return
  const layers = props.layers || {}
  for (const key of ['grid', 'cells', 'highlight', 'context', 'truth', 'methods']) {
    map.getSource(`exp-${key}`).setData(layers[key] || emptyCollection())
  }
}

function refreshFit() {
  if (!ready || !props.fit || props.fit.token === appliedFitToken) return
  appliedFitToken = props.fit.token
  if (props.fit.bounds) map.fitBounds(props.fit.bounds, { padding: 60, maxZoom: 13, duration: 500 })
}

onMounted(() => {
  map = new MapLibreMap({
    container: container.value,
    style: buildStyle(props.basemap, props.grayscale),
    center: [-4.5, 48.3],
    zoom: 7
  })
  map.addControl(new NavigationControl(), 'top-right')
  map.on('load', () => {
    build()
    ready = true
    refreshData()
    refreshFit()
  })
})

onBeforeUnmount(() => {
  if (map) map.remove()
})

watch(() => props.layers, refreshData)
watch(() => props.fit, refreshFit)
watch(() => props.basemap, id => {
  if (!ready) return
  applyBasemap(map, id, props.grayscale)
  applyInk()
})
watch(() => props.grayscale, on => {
  if (ready) applyBasemap(map, props.basemap, on)
})
</script>

<style scoped>
.experiment-map {
  height: 100%;
  width: 100%;
}
</style>
