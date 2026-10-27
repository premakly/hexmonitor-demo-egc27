<template>
  <section class="vista">
    <p v-if="explanation.status !== 'ok'" class="hint failed-note">
      VISTA settled on no behaviour and function for this gap: nothing was imputed.
    </p>

    <template v-else>
      <div class="stage">
        <h4><span class="stage-no">1</span> Behaviour <span class="module">M4</span></h4>
        <div class="chips">
          <span v-for="(value, key) in b.attributes" :key="key" class="chip" :title="value">
            <span class="chip-key">{{ ATTRIBUTE_LABELS[key] || key }}</span> {{ short(value, key) }}
          </span>
        </div>

        <div v-if="b.support && b.support.length" class="support">
          <div v-for="s in b.support" :key="s.node" class="support-row" :title="s.node">
            <span class="support-label">{{ nodeLabel(s.node, b.id) }}</span>
            <span class="support-bar"><span :style="{ width: `${(100 * s.weight) / maxWeight}%` }"></span></span>
            <span class="support-weight mono">{{ s.weight }}</span>
          </div>
        </div>
        <details v-else-if="b.support_text" class="more">
          <summary>Graph support</summary>
          <p>{{ b.support_text }}</p>
        </details>

        <p v-if="b.justification" class="text">{{ b.justification }}</p>
        <p v-if="b.resolution" class="note">{{ b.resolution }}</p>
      </div>

      <div class="stage">
        <h4><span class="stage-no">2</span> Function <span class="module">M5</span></h4>
        <p v-if="f.description" class="text">{{ f.description }}</p>
        <p v-if="f.reasoning" class="text">{{ f.reasoning }}</p>
        <details v-if="f.statistical_support" class="more">
          <summary>Statistical support</summary>
          <p>{{ f.statistical_support }}</p>
        </details>
        <details v-if="f.code" class="more code-block">
          <summary>Generated code</summary>
          <pre class="mono">{{ f.code }}</pre>
        </details>
      </div>

      <div v-if="e" class="stage">
        <h4><span class="stage-no">3</span> Explanation <span class="module">M6</span></h4>
        <p v-if="e.operational" class="text">{{ e.operational }}</p>
        <p v-if="e.regulatory" class="note">Regulatory rule: {{ e.regulatory }}</p>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  explanation: { type: Object, required: true }
})

const ATTRIBUTE_LABELS = {
  speed_profile: 'speed',
  course_change: 'course',
  heading_fluctuation: 'heading',
  intent: 'intent',
  duration: 'duration'
}

// Static graph nodes ("vs_<attribute>_<value>"), multi-word attributes first.
const STATIC_NODE = /^vs_(navigation_status|vessel_type|spatial_context|length|width|draught|destination|[a-z]+)_(.+)$/

const b = computed(() => props.explanation.behaviour || {})
const f = computed(() => props.explanation.function || {})
const e = computed(() => props.explanation.explanation)
const maxWeight = computed(() => Math.max(1, ...(b.value.support || []).map(s => s.weight)))

// The model's own wording, e.g. "stable (the vessel is maintaining…)": the
// chip shows the label before the parenthesis, the full text on hover.
function short(value, key) {
  if (key === 'duration') return `${value} s`
  return String(value).split(' (')[0]
}

function nodeLabel(node, selected) {
  if (node === selected) return 'chosen behaviour'
  if (node.startsWith('vb_')) return 'related behaviour'
  const match = STATIC_NODE.exec(node)
  return match ? `${match[1].replace(/_/g, ' ')}: ${match[2]}` : node
}
</script>

<style scoped>
.vista { display: flex; flex-direction: column; gap: 10px; }
.stage { display: flex; flex-direction: column; gap: 6px; }
.stage h4 { margin: 0; font-size: 11px; font-weight: 600; color: var(--text-dim); display: flex; align-items: center; gap: 6px; }
.stage-no {
  width: 15px; height: 15px; border-radius: 50%; background: #60a5fa; color: #0a0b0d;
  font-size: 10px; display: inline-flex; align-items: center; justify-content: center;
}
.module { font-weight: 400; color: var(--text-faint); }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { font-size: 11px; padding: 2px 6px; border-radius: var(--radius); background: var(--bg-2); border: 1px solid var(--border-soft); color: var(--text); }
.chip-key { color: var(--text-faint); }
.support { display: flex; flex-direction: column; gap: 3px; }
.support-row { display: grid; grid-template-columns: 1fr 70px 18px; gap: 6px; align-items: center; font-size: 11px; color: var(--text-dim); }
.support-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.support-bar { height: 5px; background: var(--bg-2); border-radius: 3px; overflow: hidden; }
.support-bar span { display: block; height: 100%; background: #60a5fa; }
.support-weight { text-align: right; color: var(--text-faint); }
.text { margin: 0; font-size: 11px; color: var(--text-dim); line-height: 1.45; }
.note { margin: 0; font-size: 10px; color: var(--text-faint); font-style: italic; }
.more { font-size: 11px; color: var(--text-dim); }
.more summary { cursor: pointer; color: var(--text-faint); }
.more p { margin: 4px 0 0; line-height: 1.45; }
.code-block pre {
  margin: 4px 0 0; padding: 6px 8px; font-size: 10px; line-height: 1.4; overflow-x: auto;
  background: var(--bg-2); border: 1px solid var(--border-soft); border-radius: var(--radius); color: var(--text);
}
.hint { color: var(--text-faint); font-size: 11px; margin: 0; }
</style>
