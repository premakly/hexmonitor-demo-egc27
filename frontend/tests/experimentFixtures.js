// A miniature experiment, as the backend's /experiment endpoints answer it.
export const CELLS = ['871841443ffffff', '871841441ffffff']
export const ASTAR_CELL = '871841440ffffff'
const [P, Q, R] = ['871841442ffffff', '871841444ffffff', '871841445ffffff']

// A small explored tree: the kept branch A>B>C, a finished rival A>B>B,
// a branch pruned at its first step, and one that ran out of steps.
export function walkOf() {
  const node = (id, parent, cell, depth, extra = {}) => ({
    id, parent, cell, depth, reason: null, outcome: null, probability: null, abandoned_reason: null, ...extra
  })
  return {
    probability: 0.4,
    llm_calls: 9,
    steps: [
      { step: 1, from: CELLS[0], to: P, move: 'N', reason: 'holds course' },
      { step: 2, from: P, to: CELLS[1], move: 'NE', reason: 'direct to destination' }
    ],
    tree: {
      nodes: [
        node(0, null, CELLS[0], 0),
        node(1, 0, P, 1, { reason: 'holds course' }),
        node(2, 1, CELLS[1], 2, { reason: 'direct to destination', outcome: 'kept', probability: 0.4 }),
        node(3, 1, P, 2, { reason: 'waits', outcome: 'finished', probability: 0.2 }),
        // A branch pruned early can carry a higher partial probability than the
        // final answer (fewer factors below 1): the kept branch must still lead.
        node(4, 0, Q, 1, { reason: 'turns away', outcome: 'pruned', probability: 0.6, abandoned_reason: 'pruned, less probable' }),
        node(5, 0, R, 1, { reason: 'wanders', outcome: 'step_limit', probability: 0.01 })
      ],
      counts: { branches: 4, finished: 2, pruned: 1, step_limit: 1, abandoned: 0, max_depth: 2 }
    }
  }
}

// What vista_adapter extracts from VISTA's results for one gap.
export function vistaExplanationOf(overrides = {}) {
  return {
    status: 'ok',
    behaviour: {
      id: 'vb_7',
      attributes: {
        speed_profile: 'stable (the vessel keeps a consistent speed)',
        course_change: 'slight turn to the right (gradual)',
        intent: 'navigating',
        duration: '13300~13350'
      },
      support: [
        { node: 'vb_7', weight: 5 },
        { node: 'vs_navigation_status_Under way using engine', weight: 3 },
        { node: 'vs_length_[150, 200) m', weight: 1 }
      ],
      support_text: 'vb_7 [w=5], …',
      justification: 'Consistent with the neighbouring segments.',
      resolution: "The model answered '4', read as index 4."
    },
    function: {
      id: 'vf_1',
      description: 'Linear path between start and end.',
      code: 'def spatial_function(start, end, Time_interval):\n    return []',
      statistical_support: '95% likely.',
      reasoning: 'Fits a stable speed.'
    },
    explanation: { operational: 'Typical of a cargo vessel.', regulatory: 'Undetermined' },
    ...overrides
  }
}

export function overviewOf(overrides = {}) {
  return {
    sizes: [2, 4], levels: ['facile', 'difficile'], methods: ['vista', 'hexa', 'linear'],
    summary: [
      { method: 'hexa', size_cells: 2, level: 'tous', n_ok: 38, failure_pct: 5, mean_km: 1.2, ci_low: 0.9, ci_high: 1.5, frechet_km: 1.8 },
      { method: 'linear', size_cells: 2, level: 'facile', n_ok: 20, failure_pct: 0, mean_km: 0.3, ci_low: 0.2, ci_high: 0.4, frechet_km: 0.4 },
      { method: 'hexa', size_cells: 4, level: 'tous', n_ok: 38, failure_pct: 5, mean_km: 3.6, ci_low: 2.3, ci_high: 4.9, frechet_km: 5.6 }
    ],
    tests: [
      { size_cells: 2, a: 'vista', b: 'hexa', n: 35, wins_a_pct: 20, rank_biserial: 0.72, p_holm: 0.0001 },
      { size_cells: 'toutes', a: 'vista', b: 'hexa', n: 68, wins_a_pct: 34, rank_biserial: 0.28, p_holm: 0.093 }
    ],
    exports: ['summary', 'tests'],
    results_built_at: '2026-10-16T08:00:00',
    ...overrides
  }
}

export function gapOf(id, overrides = {}) {
  return {
    gap_id: id, mmsi: Number(id.split('_')[0]), level: 'facile', size_cells: 2, n_removed: 2,
    duration_h: 0.5, length_km: 2.2,
    methods: { vista: { status: 'ok', mean_km: 2.1, frechet_km: 2.5 }, hexa: { status: 'failed', mean_km: null, frechet_km: null } },
    ...overrides
  }
}

export function detailOf(overrides = {}) {
  const track = Array.from({ length: 10 }, (_, i) => ({ idx: i, ts: 1000 + i * 600, lat: 46 + i * 0.01, lon: -3, sog: 10, cog: 0 }))
  return {
    gap: { gap_id: '111_c2', level: 'facile', size_cells: 2, n_removed: 2, length_km: 2.2, idx_start: 4, idx_end: 5, cells: CELLS },
    track,
    truth: track.filter(p => p.idx === 4 || p.idx === 5),
    methods: [
      { method: 'vista', status: 'ok', reason: null, path: null, tokens: null, latency_s: 1700,
        points: [{ idx: 4, ts: 3400, lat: 46.04, lon: -2.99 }, { idx: 5, ts: 4000, lat: 46.05, lon: -2.99 }],
        metrics: { mean_km: 2.1, frechet_km: 2.5 }, alternatives: [], explanation: vistaExplanationOf() },
      { method: 'hexa', status: 'ok', reason: null, path: CELLS, tokens: 640, latency_s: 12.5,
        points: [{ idx: 4, ts: 3400, lat: 46.04, lon: -3.01 }, { idx: 5, ts: 4000, lat: 46.05, lon: -3.01 }],
        metrics: { mean_km: 1.2, frechet_km: 1.5 },
        // As the cache can hold them: the kept path is not necessarily listed first.
        alternatives: [{ path: [CELLS[1], CELLS[0]], probability: 0.7 }, { path: CELLS, probability: 0.6 }],
        walk: walkOf() },
      { method: 'linear', status: 'failed', reason: 'no usable choice', path: null, tokens: 0, latency_s: 0,
        points: [], metrics: null, alternatives: [] },
      { method: 'astar', status: 'ok', reason: null, path: [CELLS[0], ASTAR_CELL, CELLS[1]], tokens: 0, latency_s: 0,
        points: [{ idx: 4, ts: 3400, lat: 46.04, lon: -2.98 }, { idx: 5, ts: 4000, lat: 46.05, lon: -2.98 }],
        metrics: { mean_km: 0.9, frechet_km: 1.1 }, alternatives: [] },
      { method: 'oracle', status: 'ok', reason: null, path: CELLS, tokens: 0, latency_s: 0,
        points: [{ idx: 4, ts: 3400, lat: 46.04, lon: -3.0 }, { idx: 5, ts: 4000, lat: 46.05, lon: -3.0 }],
        metrics: { mean_km: 0.6, frechet_km: 0.7 }, alternatives: [] }
    ],
    ...overrides
  }
}

// A stand-in backend: records calls, answers from the fixtures.
export function fakeApi({ overview = overviewOf(), gaps = null, failOverview = null } = {}) {
  const calls = []
  const list = gaps || { 2: [gapOf('111_c2'), gapOf('222_c2', { level: 'difficile' })], 4: [gapOf('111_c4', { size_cells: 4 })] }
  return {
    calls,
    experiment: async () => {
      calls.push(['experiment'])
      if (failOverview) throw new Error(failOverview)
      return overview
    },
    experimentGaps: async params => {
      calls.push(['gaps', params])
      const rows = (list[params.size] || []).filter(g => !params.level || g.level === params.level)
      return { gaps: rows }
    },
    experimentGap: async id => {
      calls.push(['gap', id])
      return detailOf({ gap: { ...detailOf().gap, gap_id: id } })
    },
    experimentExportUrl: name => `/api/experiment/export/${name}.csv`
  }
}
