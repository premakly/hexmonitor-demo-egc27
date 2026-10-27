<template>
  <div class="experiment">
    <p v-if="exp.overviewError.value" class="unavailable">{{ exp.overviewError.value }}</p>

    <template v-else>
      <aside class="side left">
        <ExperimentGapList
          :gaps="exp.gaps.value"
          :methods="exp.methods.value"
          :sizes="exp.overview.value ? exp.overview.value.sizes : []"
          :levels="exp.overview.value ? exp.overview.value.levels : []"
          :size="exp.size.value"
          :level="exp.level.value"
          :selected-id="exp.selectedId.value"
          :loading="exp.gapsLoading.value"
          :error="exp.gapsError.value"
          @update:size="exp.setSize"
          @update:level="exp.setLevel"
          @select="exp.select"
        />
      </aside>

      <div class="map-area">
        <ExperimentMap :basemap="basemap" :grayscale="grayscale" :layers="exp.layers.value" :fit="exp.fit.value" />
        <div class="map-toolbar">
          <div class="replay-badge" title="Results are read from the experiment's files; no model is called.">Replay</div>
          <BasemapPicker
            :model-value="basemap" :grayscale="grayscale"
            @update:model-value="$emit('update:basemap', $event)"
            @update:grayscale="$emit('update:grayscale', $event)"
          />
        </div>
      </div>

      <aside class="side right">
        <p v-if="exp.detailError.value" class="error">{{ exp.detailError.value }}</p>
        <ExperimentGapDetail
          v-else-if="exp.detail.value"
          :detail="exp.detail.value"
          :enabled="exp.enabled.value"
          :show-alternatives="exp.showAlternatives.value"
          @toggle-method="exp.toggleMethod"
          @toggle-alternatives="exp.toggleAlternatives"
        />
        <ExperimentReasoning
          v-if="exp.walk.value || exp.vistaExplanation.value"
          :walk="exp.walk.value"
          :vista="exp.vistaExplanation.value"
          @highlight-cell="exp.setHighlightCell"
          @select-branch="exp.selectBranch"
        />
        <ExperimentResults
          v-if="exp.overview.value"
          :size="exp.size.value"
          :summary="exp.overview.value.summary"
          :tests="exp.overview.value.tests"
          :exports="exp.overview.value.exports"
          :export-url="api.experimentExportUrl"
          :built-at="exp.overview.value.results_built_at"
          :can-export-gaps="exp.gaps.value.length > 0"
          @export-gaps="downloadGaps"
        />
      </aside>
    </template>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'

import { createExperimentStore } from '../experimentStore.js'
import BasemapPicker from './BasemapPicker.vue'
import ExperimentGapDetail from './ExperimentGapDetail.vue'
import ExperimentGapList from './ExperimentGapList.vue'
import ExperimentMap from './ExperimentMap.vue'
import ExperimentResults from './ExperimentResults.vue'
import ExperimentReasoning from './ExperimentReasoning.vue'

const props = defineProps({
  api: { type: Object, required: true },
  basemap: { type: String, default: 'carto-dark' },
  grayscale: { type: Boolean, default: true },
  // The trajectory to open first: { vessel: MMSI, size: cells or null }.
  initialGap: { type: Object, default: null }
})

// The base map is the app's own setting, shared with the Map view: the
// choice is passed up rather than kept here, so both views stay in step.
defineEmits(['update:basemap', 'update:grayscale'])

const exp = createExperimentStore(props.api, { initialGap: props.initialGap })

function downloadGaps() {
  const blob = new Blob([exp.gapsCsv()], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `experiment_gaps_c${exp.size.value}${exp.level.value ? `_${exp.level.value}` : ''}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(exp.init)

defineExpose({ exp })
</script>

<style scoped>
.experiment {
  flex: 1;
  display: grid;
  grid-template-columns: 300px 1fr 360px;
  min-height: 0;
}
.side {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  background: var(--bg-1);
  min-height: 0;
}
.side.left { border-right: 1px solid var(--border); }
.side.right { border-left: 1px solid var(--border); }
.map-area { position: relative; min-width: 0; }
.map-toolbar {
  position: absolute; top: 12px; left: 12px; z-index: 5;
  display: flex; align-items: center; gap: 10px;
}
.replay-badge {
  font-size: 11px; padding: 3px 8px; border-radius: var(--radius);
  background: var(--bg-2); border: 1px solid var(--border); color: var(--text-dim);
}
.unavailable, .error { color: var(--bad); font-size: 12px; padding: 16px; margin: 0; }
</style>
