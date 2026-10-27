<template>
  <section class="reasoning">
    <div class="reasoning-head">
      <h3>Reasoning</h3>
      <nav class="tabs">
        <button
          v-for="t in tabs" :key="t.id" type="button" class="tab" :class="{ active: t.id === current }"
          :style="t.id === current ? { borderColor: t.colour } : {}" @click="chosen = t.id"
        >{{ t.label }}</button>
      </nav>
    </div>

    <ExperimentWalk
      v-if="current === 'hexa'"
      :walk="walk"
      @highlight-cell="$emit('highlight-cell', $event)"
      @select-branch="$emit('select-branch', $event)"
    />
    <ExperimentVistaReasoning v-else-if="current === 'vista'" :explanation="vista" />
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

import { methodStyle } from '../lib/experiment.js'
import ExperimentVistaReasoning from './ExperimentVistaReasoning.vue'
import ExperimentWalk from './ExperimentWalk.vue'

const props = defineProps({
  walk: { type: Object, default: null },
  vista: { type: Object, default: null }
})

defineEmits(['highlight-cell', 'select-branch'])

const tabs = computed(() => [
  props.walk && { id: 'hexa', ...methodStyle('hexa') },
  props.vista && { id: 'vista', ...methodStyle('vista') }
].filter(Boolean))

// The tab chosen stays chosen from gap to gap, as long as that method has
// something to show; otherwise the first available one is shown.
const chosen = ref(null)
const current = computed(() =>
  tabs.value.some(t => t.id === chosen.value) ? chosen.value : (tabs.value[0] && tabs.value[0].id)
)
</script>

<style scoped>
.reasoning { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border-soft); padding-top: 12px; }
.reasoning-head { display: flex; justify-content: space-between; align-items: center; }
.reasoning h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--text-dim); }
.tabs { display: flex; gap: 4px; }
.tab {
  background: none; border: 1px solid var(--border-soft); border-radius: var(--radius);
  color: var(--text-dim); font-size: 11px; padding: 2px 8px; cursor: pointer;
}
.tab.active { color: var(--text); background: var(--bg-2); }
</style>
