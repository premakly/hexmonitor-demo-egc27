<template>
  <div class="demo">
    <header class="demo-bar">
      <div class="brand">
        <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
          <polygon points="12,2 21,7 21,17 12,22 3,17 3,7" />
        </svg>
        <span class="brand-name">Demo EGC27</span>
        <span class="brand-sub">Hex Monitor · LLM completion of AIS gaps, VISTA against Hexa</span>
      </div>
      <span class="replay-note" title="Every result is read from the experiment's files; no model is called.">
        Replay of the experiment
      </span>
    </header>

    <ExperimentView
      :api="api" :basemap="basemap" :grayscale="grayscale" :initial-gap="initialGap"
      @update:basemap="setBasemap" @update:grayscale="setGrayscale"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'

import ExperimentView from './components/ExperimentView.vue'
import { DEMO_DEFAULTS } from './demo.config.js'
import { createApi } from './lib/api.js'
import { basemapById } from './lib/basemaps.js'

const props = defineProps({
  api: { type: Object, default: () => createApi() },
  defaults: { type: Object, default: () => DEMO_DEFAULTS }
})
const api = props.api

// Every arrival starts from the demo's own base map: a visitor may change it
// while browsing, but the choice is deliberately not remembered.
const basemap = ref(basemapById(props.defaults.basemap).id)
const grayscale = ref(Boolean(props.defaults.grayscale))
const initialGap = { vessel: props.defaults.vessel ?? null, size: props.defaults.size ?? null }

function setBasemap(id) {
  basemap.value = basemapById(id).id
}

function setGrayscale(on) {
  grayscale.value = Boolean(on)
}

defineExpose({ basemap, grayscale })
</script>

<style scoped>
.demo { height: 100%; display: flex; flex-direction: column; }
.demo-bar {
  display: flex; justify-content: space-between; align-items: center; gap: 16px;
  padding: 8px 14px; background: var(--bg-1); border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 8px; min-width: 0; }
.brand-mark { width: 18px; height: 18px; fill: none; stroke: var(--accent); stroke-width: 2; }
.brand-name { font-weight: 600; font-size: 14px; }
.brand-sub { color: var(--text-faint); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.replay-note {
  font-size: 11px; color: var(--text-dim); padding: 3px 8px;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--bg-2); white-space: nowrap;
}
</style>
