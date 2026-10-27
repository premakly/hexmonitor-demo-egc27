<template>
  <div class="basemap-picker">
    <div class="basemap-options" role="radiogroup" aria-label="Base map">
      <button
        v-for="b in basemaps"
        :key="b.id"
        type="button"
        class="basemap-option"
        :class="{ active: b.id === modelValue }"
        role="radio"
        :aria-checked="b.id === modelValue"
        @click="$emit('update:modelValue', b.id)"
      >
        {{ b.label }}
      </button>
    </div>
    <label class="grayscale-toggle">
      <input type="checkbox" :checked="grayscale" @change="$emit('update:grayscale', $event.target.checked)" />
      <span>Grayscale</span>
    </label>
  </div>
</template>

<script setup>
import { BASEMAPS } from '../lib/basemaps.js'

defineProps({
  modelValue: { type: String, required: true },
  grayscale: { type: Boolean, default: true }
})
defineEmits(['update:modelValue', 'update:grayscale'])

const basemaps = BASEMAPS
</script>

<style scoped>
.basemap-picker {
  display: flex;
  align-items: center;
  gap: 12px;
}

.basemap-options {
  display: flex;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2px;
  gap: 2px;
}

.basemap-option {
  border: none;
  background: transparent;
  color: var(--text-dim);
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1;
}

.basemap-option:hover {
  color: var(--text);
}

.basemap-option.active {
  background: var(--bg-3);
  color: var(--text);
}

.grayscale-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-dim);
  white-space: nowrap;
}

.grayscale-toggle input {
  accent-color: var(--accent);
}
</style>
