<template>
  <div class="gap-list">
    <div class="filters">
      <label>
        <span>Gap size</span>
        <select class="size-select" :value="size" @change="$emit('update:size', Number($event.target.value))">
          <option v-for="s in sizes" :key="s" :value="s">{{ s }} cells</option>
        </select>
      </label>
      <label>
        <span>Level</span>
        <select class="level-select" :value="level || ''" @change="$emit('update:level', $event.target.value || null)">
          <option value="">All</option>
          <option v-for="lv in levels" :key="lv" :value="lv">{{ lv }}</option>
        </select>
      </label>
    </div>

    <div class="legend">
      <span v-for="(m, i) in methods" :key="m" class="legend-item">
        <span class="swatch" :style="{ background: methodStyle(m, i).colour }"></span>{{ methodStyle(m, i).label }}
      </span>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="hint">Loading…</p>
    <p v-else-if="!gaps.length" class="hint">No gap for these filters.</p>

    <ul v-else class="gap-rows">
      <li v-for="g in gaps" :key="g.gap_id">
        <button
          type="button" class="gap-row" :class="{ current: g.gap_id === selectedId }"
          @click="$emit('select', g.gap_id)"
        >
          <span class="gap-main">
            <span class="mono">{{ g.mmsi }}</span>
            <span class="gap-meta">{{ g.level }} · {{ formatDuration(g.duration_h) }} · {{ formatKm(g.length_km) }}</span>
          </span>
          <span class="gap-methods">
            <span
              v-for="(m, i) in methods" :key="m" class="method-dot"
              :class="dotClass(g.methods[m])"
              :style="dotStyle(g.methods[m], i, m)"
              :title="dotTitle(g.methods[m], m)"
            ></span>
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { formatKm, methodStyle } from '../lib/experiment.js'

defineProps({
  gaps: { type: Array, default: () => [] },
  methods: { type: Array, default: () => [] },
  sizes: { type: Array, default: () => [] },
  levels: { type: Array, default: () => [] },
  size: { type: Number, default: null },
  level: { type: String, default: null },
  selectedId: { type: String, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null }
})

defineEmits(['update:size', 'update:level', 'select'])

function formatDuration(hours) {
  if (hours === null || hours === undefined) return '—'
  return hours < 1 ? `${Math.round(hours * 60)} min` : `${hours.toFixed(1)} h`
}

function dotClass(result) {
  if (!result) return 'missing'
  return result.status === 'ok' ? 'ok' : 'failed'
}

function dotStyle(result, index, method) {
  return result && result.status === 'ok' ? { background: methodStyle(method, index).colour } : {}
}

function dotTitle(result, method) {
  const label = methodStyle(method).label
  if (!result) return `${label}: not run`
  if (result.status !== 'ok') return `${label}: failed`
  return result.mean_km === null || result.mean_km === undefined ? label : `${label}: ${formatKm(result.mean_km)}`
}
</script>

<style scoped>
.gap-list { display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.filters { display: flex; gap: 10px; }
.filters label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--text-dim); flex: 1; }
.filters select {
  background: var(--bg-2); border: 1px solid var(--border); border-radius: var(--radius);
  color: var(--text); padding: 5px 6px; font-size: 12px;
}
.legend { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11px; color: var(--text-dim); }
.legend-item { display: flex; align-items: center; gap: 5px; }
.swatch { width: 10px; height: 3px; border-radius: 2px; }
.hint { color: var(--text-faint); font-size: 12px; margin: 0; }
.error { color: var(--bad); font-size: 12px; margin: 0; }
.gap-rows { list-style: none; margin: 0; padding: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.gap-row {
  width: 100%; display: flex; justify-content: space-between; align-items: center; gap: 8px;
  background: none; border: 1px solid transparent; border-radius: var(--radius);
  color: var(--text); padding: 6px 8px; cursor: pointer; text-align: left;
}
.gap-row:hover { background: var(--bg-2); }
.gap-row.current { background: var(--bg-3); border-color: var(--border); }
.gap-main { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.gap-meta { color: var(--text-faint); font-size: 11px; }
.gap-methods { display: flex; gap: 3px; }
.method-dot { width: 8px; height: 8px; border-radius: 50%; border: 1px solid var(--border); }
.method-dot.failed { background: var(--bad); border-color: var(--bad); opacity: 0.8; }
.method-dot.missing { background: transparent; }
</style>
