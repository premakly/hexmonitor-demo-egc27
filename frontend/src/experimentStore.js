// State of the Experiment view: what is loaded, what is selected, what is
// shown. Read-only over the backend's /experiment endpoints, which replay the
// experiment's files and never call the model.

import { computed, ref, shallowRef } from 'vue'

import { boundsOf } from './lib/geo.js'
import { experimentLayers, gapTableColumns, highlightLayer, toCsv } from './lib/experiment.js'

export function createExperimentStore(api) {
  const overview = shallowRef(null)
  const overviewError = ref(null)
  const size = ref(null)
  const level = ref(null)
  const gaps = shallowRef([])
  const gapsLoading = ref(false)
  const gapsError = ref(null)
  const selectedId = ref(null)
  const detail = shallowRef(null)
  const detailError = ref(null)
  const enabled = ref([])
  // Hexa's other finished walks: hidden unless asked for, since cells the
  // line does not cross read as part of the completion.
  const showAlternatives = ref(false)
  // From Hexa's reasoning panel: the cell of a hovered step, a picked branch.
  const highlightCell = ref(null)
  const branch = shallowRef(null)
  const fit = shallowRef(null)

  let gapsRequest = 0
  let detailRequest = 0

  const methods = computed(() => (overview.value ? overview.value.methods : []))
  const layers = computed(() => ({
    ...experimentLayers(detail.value, enabled.value, null, showAlternatives.value),
    highlight: highlightLayer(highlightCell.value, branch.value)
  }))
  const walk = computed(() => {
    const hexa = detail.value && detail.value.methods.find(m => m.method === 'hexa')
    return (hexa && hexa.walk) || null
  })
  const vistaExplanation = computed(() => {
    const vista = detail.value && detail.value.methods.find(m => m.method === 'vista')
    return (vista && vista.explanation) || null
  })

  async function init() {
    try {
      overview.value = await api.experiment()
      overviewError.value = null
    } catch (e) {
      overviewError.value = e.message
      return
    }
    enabled.value = [...overview.value.methods]
    size.value = overview.value.sizes[0] ?? null
    await loadGaps({ selectFirst: true })
  }

  // A later request supersedes an earlier one still in flight: switching
  // filters quickly must not let a slow, stale answer overwrite a newer one.
  async function loadGaps({ selectFirst = false } = {}) {
    const token = ++gapsRequest
    gapsLoading.value = true
    try {
      const body = await api.experimentGaps({ size: size.value, level: level.value })
      if (token !== gapsRequest) return
      gaps.value = body.gaps
      gapsError.value = null
    } catch (e) {
      if (token !== gapsRequest) return
      gaps.value = []
      gapsError.value = e.message
    } finally {
      if (token === gapsRequest) gapsLoading.value = false
    }
    const stillListed = gaps.value.some(g => g.gap_id === selectedId.value)
    if ((selectFirst || !stillListed) && gaps.value.length) await select(gaps.value[0].gap_id)
    else if (!gaps.value.length) clearSelection()
  }

  async function select(gapId) {
    const token = ++detailRequest
    selectedId.value = gapId
    highlightCell.value = null
    branch.value = null
    try {
      const body = await api.experimentGap(gapId)
      if (token !== detailRequest) return
      detail.value = body
      detailError.value = null
      fit.value = { bounds: boundsOf(experimentLayers(body).context) || boundsOf(experimentLayers(body).truth), token: `${gapId}-${token}` }
    } catch (e) {
      if (token !== detailRequest) return
      detail.value = null
      detailError.value = e.message
    }
  }

  function clearSelection() {
    detailRequest++
    selectedId.value = null
    detail.value = null
  }

  async function setSize(value) {
    size.value = value
    await loadGaps()
  }

  async function setLevel(value) {
    level.value = value
    await loadGaps()
  }

  function toggleMethod(method) {
    enabled.value = enabled.value.includes(method)
      ? enabled.value.filter(m => m !== method)
      : [...enabled.value, method]
  }

  function setHighlightCell(cell) {
    highlightCell.value = cell
  }

  function selectBranch(cells) {
    branch.value = cells
  }

  function toggleAlternatives() {
    showAlternatives.value = !showAlternatives.value
  }

  function gapsCsv() {
    return toCsv(gaps.value, gapTableColumns(methods.value))
  }

  return {
    overview, overviewError, size, level, gaps, gapsLoading, gapsError,
    selectedId, detail, detailError, enabled, showAlternatives, fit, methods, layers,
    walk, vistaExplanation, highlightCell, branch,
    init, loadGaps, select, setSize, setLevel, toggleMethod, toggleAlternatives,
    setHighlightCell, selectBranch, gapsCsv
  }
}
