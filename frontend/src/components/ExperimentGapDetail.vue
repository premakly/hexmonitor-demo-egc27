<template>
  <div class="gap-detail">
    <h3>
      Gap <span class="mono">{{ detail.gap.gap_id }}</span>
    </h3>
    <p class="gap-facts">
      {{ detail.gap.level }} · {{ detail.gap.size_cells }} cells · {{ detail.gap.n_removed }} points removed ·
      {{ formatKm(detail.gap.length_km) }}
    </p>

    <table class="methods">
      <thead>
        <tr><th></th><th>Method</th><th>Error</th><th>Fréchet</th><th>Cost</th></tr>
      </thead>
      <tbody>
        <tr v-for="(m, i) in detail.methods" :key="m.method" :class="{ failed: m.status !== 'ok' }">
          <td>
            <input
              type="checkbox" class="method-toggle" :checked="enabled.includes(m.method)"
              :style="{ accentColor: methodStyle(m.method, i).colour }"
              @change="$emit('toggle-method', m.method)"
            />
          </td>
          <td>
            <span class="swatch" :style="{ background: methodStyle(m.method, i).colour }"></span>
            {{ methodStyle(m.method, i).label }}
          </td>
          <template v-if="m.status === 'ok'">
            <td class="mono">{{ formatKm(m.metrics?.mean_km) }}</td>
            <td class="mono">{{ formatKm(m.metrics?.frechet_km) }}</td>
            <td class="mono">{{ costLabel(m) }}</td>
          </template>
          <td v-else colspan="3" class="reason" :title="m.reason || ''">failed{{ m.reason ? `: ${m.reason}` : '' }}</td>
        </tr>
      </tbody>
    </table>

    <p v-if="cellMethods.length" class="hint">
      Cells are drawn in each method's colour: {{ cellMethods.join(', ') }}. A line runs through its own method's cells.
    </p>
    <label v-if="otherWalks > 0" class="alternatives-toggle">
      <input type="checkbox" :checked="showAlternatives" @change="$emit('toggle-alternatives')" />
      <span>Show Hexa's {{ otherWalks }} other finished walk{{ otherWalks > 1 ? 's' : '' }} (fainter)</span>
    </label>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import { formatKm, methodStyle } from '../lib/experiment.js'

const props = defineProps({
  detail: { type: Object, required: true },
  enabled: { type: Array, default: () => [] },
  showAlternatives: { type: Boolean, default: false }
})

defineEmits(['toggle-method', 'toggle-alternatives'])

// The methods whose cells are on the map right now: shown, succeeded, with a path.
const cellMethods = computed(() =>
  props.detail.methods
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.status === 'ok' && m.path && m.path.length && props.enabled.includes(m.method))
    .map(({ m, i }) => methodStyle(m.method, i).label)
)

const otherWalks = computed(() => {
  const hexa = props.detail.methods.find(m => m.method === 'hexa')
  if (!hexa || hexa.status !== 'ok') return 0
  const kept = JSON.stringify(hexa.path)
  return (hexa.alternatives || []).filter(a => JSON.stringify(a.path) !== kept).length
})

function costLabel(m) {
  const parts = []
  if (m.tokens) parts.push(`${Math.round(m.tokens)} tok`)
  if (m.latency_s !== null && m.latency_s !== undefined && m.latency_s >= 0.05) {
    parts.push(m.latency_s < 60 ? `${m.latency_s.toFixed(1)} s` : `${(m.latency_s / 60).toFixed(1)} min`)
  }
  return parts.join(' · ') || '—'
}
</script>

<style scoped>
.gap-detail h3 { margin: 0 0 4px; font-size: 13px; font-weight: 600; }
.gap-facts { margin: 0 0 10px; font-size: 11px; color: var(--text-faint); }
.methods { width: 100%; border-collapse: collapse; font-size: 12px; }
.methods th { text-align: left; font-weight: 500; color: var(--text-faint); font-size: 11px; padding: 3px 4px; }
.methods td { padding: 4px; border-top: 1px solid var(--border-soft); vertical-align: middle; }
.methods tr.failed td { color: var(--text-faint); }
.reason { font-size: 11px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.swatch { display: inline-block; width: 10px; height: 3px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }
.hint { color: var(--text-faint); font-size: 11px; margin: 8px 0 0; }
.alternatives-toggle { display: flex; align-items: center; gap: 6px; margin-top: 6px; font-size: 11px; color: var(--text-dim); }
</style>
