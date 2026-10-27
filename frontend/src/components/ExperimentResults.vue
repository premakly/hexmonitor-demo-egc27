<template>
  <div class="results">
    <div class="results-head">
      <h3>Results · {{ size }} cells</h3>
      <span v-if="builtAt" class="built" :title="`Computed ${builtAt}`">computed {{ builtAt.slice(0, 16).replace('T', ' ') }}</span>
    </div>

    <p v-if="!summary" class="hint">Not computed yet: run <code>python -m EGC27.metrics</code>.</p>

    <template v-else>
      <table class="summary">
        <thead>
          <tr><th>Level</th><th>Method</th><th>n</th><th>Fail</th><th>Error (95% CI)</th><th>Fréchet</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in summaryRows" :key="`${r.level}-${r.method}`" :class="{ total: r.level === 'tous' }">
            <td>{{ r.level === 'tous' ? 'all' : r.level }}</td>
            <td><span class="swatch" :style="{ background: methodStyle(r.method).colour }"></span>{{ methodStyle(r.method).label }}</td>
            <td class="mono">{{ r.n_ok }}</td>
            <td class="mono">{{ percent(r.failure_pct) }}</td>
            <td class="mono">{{ num(r.mean_km) }} <span class="ci">[{{ num(r.ci_low) }}; {{ num(r.ci_high) }}]</span></td>
            <td class="mono">{{ num(r.frechet_km) }}</td>
          </tr>
        </tbody>
      </table>

      <h4 v-if="testRows.length">Paired tests (Wilcoxon, Holm)</h4>
      <table v-if="testRows.length" class="tests">
        <thead><tr><th>A vs B</th><th>n</th><th>A better</th><th>r</th><th>p</th></tr></thead>
        <tbody>
          <tr v-for="t in testRows" :key="`${t.a}-${t.b}`">
            <td>{{ methodStyle(t.a).label }} vs {{ methodStyle(t.b).label }}</td>
            <td class="mono">{{ t.n }}</td>
            <td class="mono">{{ percent(t.wins_a_pct) }}</td>
            <td class="mono">{{ num(t.rank_biserial) }}</td>
            <td class="mono">{{ pValue(t.p_holm) }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <div class="exports">
      <a v-for="name in exports" :key="name" class="ghost-btn" :href="exportUrl(name)" download>{{ name }}.csv</a>
      <button type="button" class="ghost-btn export-gaps" :disabled="!canExportGaps" @click="$emit('export-gaps')">
        gaps.csv
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import { methodStyle } from '../lib/experiment.js'

const props = defineProps({
  size: { type: Number, default: null },
  summary: { type: Array, default: null },
  tests: { type: Array, default: null },
  exports: { type: Array, default: () => [] },
  exportUrl: { type: Function, default: name => name },
  builtAt: { type: String, default: null },
  canExportGaps: { type: Boolean, default: false }
})

defineEmits(['export-gaps'])

const LEVEL_ORDER = ['facile', 'difficile', 'tous']

const summaryRows = computed(() =>
  (props.summary || [])
    .filter(r => Number(r.size_cells) === props.size)
    .sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level))
)

// Only the selected size's tests; the pooled ones (size_cells "toutes")
// summarise every size and stay in the tests.csv export.
const testRows = computed(() =>
  (props.tests || []).filter(t => String(t.size_cells) === String(props.size))
)

const num = v => (v === null || v === undefined ? '—' : Number(v).toFixed(2))
const percent = v => (v === null || v === undefined ? '—' : `${Math.round(v)}%`)
const pValue = v => (v === null || v === undefined ? '—' : v < 0.001 ? '<0.001' : Number(v).toFixed(3))
</script>

<style scoped>
.results { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border-soft); padding-top: 12px; }
.results-head { display: flex; justify-content: space-between; align-items: baseline; }
.results h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--text-dim); }
.results h4 { margin: 6px 0 0; font-size: 11px; font-weight: 600; color: var(--text-dim); }
.built { font-size: 10px; color: var(--text-faint); }
.hint { color: var(--text-faint); font-size: 12px; margin: 0; }
table { width: 100%; border-collapse: collapse; font-size: 11px; }
th { text-align: left; font-weight: 500; color: var(--text-faint); padding: 3px 4px; }
td { padding: 3px 4px; border-top: 1px solid var(--border-soft); }
tr.total td { font-weight: 600; }
.ci { color: var(--text-faint); }
.swatch { display: inline-block; width: 8px; height: 3px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }
.exports { display: flex; flex-wrap: wrap; gap: 6px; }
.ghost-btn {
  font-size: 11px; padding: 4px 8px; border: 1px solid var(--border); border-radius: var(--radius);
  background: none; color: var(--text-dim); text-decoration: none; cursor: pointer;
}
.ghost-btn:disabled { opacity: 0.5; cursor: default; }
</style>
