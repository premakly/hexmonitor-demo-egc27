import { describe, expect, it } from 'vitest'

import { createExperimentStore } from '../src/experimentStore.js'
import { CELLS, fakeApi, overviewOf } from './experimentFixtures.js'

describe('experiment store', () => {
  it('starts on the first gap size with every method shown, and opens the first gap', async () => {
    const api = fakeApi()
    const exp = createExperimentStore(api)
    await exp.init()

    expect(exp.size.value).toBe(2)
    expect(exp.enabled.value).toEqual(['vista', 'hexa', 'linear'])
    expect(exp.selectedId.value).toBe('111_c2')
    expect(exp.detail.value.gap.gap_id).toBe('111_c2')
  })

  it('reports an experiment that has not been run', async () => {
    const exp = createExperimentStore(fakeApi({ failOverview: 'No experiment results found' }))
    await exp.init()

    expect(exp.overviewError.value).toContain('No experiment results')
    expect(exp.gaps.value).toEqual([])
  })

  it('reloads the list when the level changes, keeping a gap still listed', async () => {
    const api = fakeApi()
    const exp = createExperimentStore(api)
    await exp.init()
    await exp.select('222_c2')
    await exp.setLevel('difficile')

    expect(api.calls).toContainEqual(['gaps', { size: 2, level: 'difficile' }])
    expect(exp.gaps.value.map(g => g.gap_id)).toEqual(['222_c2'])
    expect(exp.selectedId.value).toBe('222_c2')
  })

  it('moves to the first gap of the new size when the selected one is gone', async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    await exp.setSize(4)

    expect(exp.selectedId.value).toBe('111_c4')
  })

  it('clears the selection when nothing is left to show', async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    await exp.setLevel('nonexistent')

    expect(exp.selectedId.value).toBe(null)
    expect(exp.detail.value).toBe(null)
  })

  it('toggles a method off and on again', async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    exp.toggleMethod('hexa')
    expect(exp.enabled.value).not.toContain('hexa')
    expect(exp.layers.value.methods.features.some(f => f.properties.method === 'hexa')).toBe(false)
    exp.toggleMethod('hexa')
    expect(exp.enabled.value).toContain('hexa')
  })

  it("hides Hexa's other walks until asked, then shows them", async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    const ranks = () => new Set(exp.layers.value.cells.features.map(f => f.properties.rank))

    expect(ranks()).toEqual(new Set([0]))
    exp.toggleAlternatives()
    expect(ranks()).toEqual(new Set([0, 1]))
  })

  it("exposes Hexa's walk and draws what its panel points at", async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()

    expect(exp.walk.value.tree.counts.branches).toBe(4)
    exp.setHighlightCell(CELLS[0])
    exp.selectBranch(CELLS)
    expect(exp.layers.value.highlight.features.map(f => f.properties.kind)).toEqual(['branch', 'branch', 'branch-line', 'cell'])
  })

  it("exposes VISTA's reasoning for the selected gap", async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    expect(exp.vistaExplanation.value.function.id).toBe('vf_1')
  })

  it('forgets the highlight when another gap is opened', async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    exp.setHighlightCell(CELLS[0])
    exp.selectBranch(CELLS)
    await exp.select('222_c2')

    expect(exp.layers.value.highlight.features).toEqual([])
  })

  it('fits the map to the gap once per selection', async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    const first = exp.fit.value
    await exp.select('222_c2')

    expect(first.bounds).toBeTruthy()
    expect(exp.fit.value.token).not.toBe(first.token)
  })

  it('a slow answer for an earlier gap does not replace a later one', async () => {
    const api = fakeApi()
    let release
    const slow = new Promise(resolve => { release = resolve })
    const original = api.experimentGap
    api.experimentGap = async id => (id === '111_c2' ? (await slow, original(id)) : original(id))
    const exp = createExperimentStore(api)
    exp.overview.value = overviewOf()

    const first = exp.select('111_c2')
    await exp.select('222_c2')
    release()
    await first

    expect(exp.selectedId.value).toBe('222_c2')
    expect(exp.detail.value.gap.gap_id).toBe('222_c2')
  })

  it('exports the listed gaps as CSV', async () => {
    const exp = createExperimentStore(fakeApi())
    await exp.init()
    const csv = exp.gapsCsv()

    expect(csv.split('\n')[0]).toContain('hexa_mean_km')
    expect(csv).toContain('222_c2')
  })
})
