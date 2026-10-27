<template>
  <section class="walk">
    <p class="walk-summary">
      {{ counts.branches }} branches explored · {{ counts.finished }} reached the far end ·
      {{ counts.pruned }} pruned · {{ counts.step_limit }} out of steps
      <template v-if="walk.llm_calls"> · {{ walk.llm_calls }} model calls</template>
    </p>

    <ol v-if="walk.steps.length" class="steps">
      <li
        v-for="s in walk.steps" :key="s.step" class="step"
        @mouseenter="$emit('highlight-cell', s.to)" @mouseleave="$emit('highlight-cell', null)"
      >
        <span class="step-move mono" :class="{ stay: s.move === 'stay' }">{{ s.move === 'stay' ? '·' : s.move }}</span>
        <span class="step-reason">{{ s.reason || 'no reason given' }}</span>
      </li>
    </ol>
    <p v-else class="hint">No branch reached the far end: nothing was kept.</p>

    <div class="tree-head">
      <span>Scenario tree</span>
      <button v-if="selectedLeaf !== null" type="button" class="link-btn clear-branch" @click="pick(null)">clear</button>
    </div>
    <div class="tree-scroll">
      <svg :width="width" :height="height" class="tree" role="img" aria-label="Branches explored by the walk">
        <path
          v-for="(e, i) in layout.edges" :key="`e${i}`"
          :d="edgePath(e)" class="edge" :class="{ kept: e.onKept, chosen: onSelected(e.to.id) }"
        />
        <circle
          v-for="n in leaves" :key="`n${n.id}`"
          :cx="px(n.x)" :cy="py(n.y)" :r="n.outcome === 'kept' ? 3.5 : 2.5"
          class="leaf" :class="[n.outcome, { selected: n.id === selectedLeaf }]"
          @click="pick(n.id)"
        >
          <title>{{ leafTitle(n) }}</title>
        </circle>
      </svg>
    </div>
    <div class="tree-legend">
      <span v-for="o in OUTCOMES" :key="o.id" class="legend-item"><span class="dot" :class="o.id"></span>{{ o.label }}</span>
    </div>
    <p class="hint">Hover a step to find its cell on the map; click a branch's end to draw it.</p>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

import { branchCells, layoutWalkTree } from '../lib/experiment.js'

const props = defineProps({
  walk: { type: Object, required: true }
})

const emit = defineEmits(['highlight-cell', 'select-branch'])

const OUTCOMES = [
  { id: 'kept', label: 'kept' },
  { id: 'finished', label: 'reached the end' },
  { id: 'pruned', label: 'pruned' },
  { id: 'step_limit', label: 'out of steps' }
]
const LABELS = {
  kept: 'Kept: the answer',
  finished: 'Reached the end, less probable',
  pruned: 'Pruned: less probable than the branches kept alive',
  step_limit: 'Ran out of steps before the far end',
  abandoned: 'Abandoned'
}

const COL = 16
const ROW = 6
const PAD = 6

const layout = computed(() => layoutWalkTree(props.walk.tree))
const counts = computed(() => props.walk.tree.counts)
const leaves = computed(() => layout.value.nodes.filter(n => n.outcome))
const width = computed(() => layout.value.depth * COL + 2 * PAD)
const height = computed(() => Math.max(layout.value.rows - 1, 0) * ROW + 2 * PAD)

const px = x => PAD + x * COL
const py = y => PAD + y * ROW

// An elbow: along the parent's row, then down to the child's, so branches
// read as splits of the line they leave.
function edgePath(e) {
  const x1 = px(e.from.x)
  const x2 = px(e.to.x)
  const y1 = py(e.from.y)
  const y2 = py(e.to.y)
  return y1 === y2 ? `M${x1},${y1}H${x2}` : `M${x1},${y1}H${(x1 + x2) / 2}V${y2}H${x2}`
}

function leafTitle(n) {
  const parts = [LABELS[n.outcome] || n.outcome, `step ${n.depth}`]
  if (n.probability !== null && n.probability !== undefined) parts.push(`p = ${n.probability.toExponential(2)}`)
  if (n.reason) parts.push(`last step: ${n.reason}`)
  return parts.join(' · ')
}

const selectedLeaf = ref(null)
const selectedPath = computed(() => {
  const ids = new Set()
  const nodes = props.walk.tree.nodes
  for (let id = selectedLeaf.value; id !== null && id !== undefined; id = nodes[id].parent) ids.add(id)
  return ids
})
const onSelected = id => selectedPath.value.has(id)

function pick(id) {
  selectedLeaf.value = id === selectedLeaf.value ? null : id
  emit('select-branch', selectedLeaf.value === null ? null : branchCells(props.walk.tree, selectedLeaf.value))
}

// A new gap brings a new walk: a branch picked in the previous one means nothing here.
watch(() => props.walk, () => {
  selectedLeaf.value = null
})
</script>

<style scoped>
.walk { display: flex; flex-direction: column; gap: 8px; }
.walk-summary { margin: 0; font-size: 11px; color: var(--text-faint); }
.steps { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 1px; max-height: 220px; overflow-y: auto; }
.step { display: grid; grid-template-columns: 26px 1fr; gap: 6px; font-size: 11px; padding: 3px 4px; border-radius: var(--radius); cursor: default; }
.step:hover { background: var(--bg-2); }
.step-move { color: #f5a524; font-weight: 600; }
.step-move.stay { color: var(--text-faint); }
.step-reason { color: var(--text-dim); }
.tree-head { display: flex; justify-content: space-between; align-items: baseline; font-size: 11px; color: var(--text-dim); }
.link-btn { background: none; border: none; color: var(--text-faint); font-size: 11px; cursor: pointer; text-decoration: underline; }
.tree-scroll { max-height: 260px; overflow: auto; background: var(--bg-2); border: 1px solid var(--border-soft); border-radius: var(--radius); }
.edge { fill: none; stroke: var(--text-faint); stroke-width: 0.8; opacity: 0.6; }
.edge.kept { stroke: #f5a524; stroke-width: 2; opacity: 1; }
.edge.chosen { stroke: var(--text); stroke-width: 1.6; opacity: 1; }
.leaf { cursor: pointer; stroke: var(--bg-1); stroke-width: 0.6; }
.leaf.kept, .dot.kept { fill: #f5a524; background: #f5a524; }
.leaf.finished, .dot.finished { fill: #fcd34d; background: #fcd34d; }
.leaf.pruned, .dot.pruned { fill: var(--text-faint); background: var(--text-faint); }
.leaf.step_limit, .dot.step_limit { fill: #f87171; background: #f87171; }
.leaf.abandoned { fill: var(--text-faint); }
.leaf.selected { stroke: var(--text); stroke-width: 1.5; }
.tree-legend { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 10px; color: var(--text-faint); }
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.hint { color: var(--text-faint); font-size: 11px; margin: 0; }
</style>
