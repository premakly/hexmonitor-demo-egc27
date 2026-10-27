import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

// The real map pulls in maplibre-gl, which needs a browser (WebGL, a worker
// built with URL.createObjectURL) that jsdom does not provide. The view's
// tests only need to see what it hands the map.
vi.mock('../src/components/ExperimentMap.vue', () => ({
  default: {
    name: 'ExperimentMap',
    props: ['basemap', 'grayscale', 'layers', 'fit'],
    template: '<div class="map-stub"></div>'
  }
}))

import ExperimentGapDetail from '../src/components/ExperimentGapDetail.vue'
import ExperimentGapList from '../src/components/ExperimentGapList.vue'
import ExperimentResults from '../src/components/ExperimentResults.vue'
import ExperimentView from '../src/components/ExperimentView.vue'
import ExperimentReasoning from '../src/components/ExperimentReasoning.vue'
import ExperimentVistaReasoning from '../src/components/ExperimentVistaReasoning.vue'
import ExperimentWalk from '../src/components/ExperimentWalk.vue'
import { CELLS, detailOf, fakeApi, gapOf, overviewOf, vistaExplanationOf, walkOf } from './experimentFixtures.js'

const listProps = (overrides = {}) => ({
  gaps: [gapOf('111_c2'), gapOf('222_c2')], methods: ['vista', 'hexa'], sizes: [2, 4],
  levels: ['facile', 'difficile'], size: 2, level: null, selectedId: '111_c2', ...overrides
})

describe('ExperimentGapList', () => {
  it('lists every gap and highlights the selected one', () => {
    const wrapper = mount(ExperimentGapList, { props: listProps() })
    const rows = wrapper.findAll('.gap-row')

    expect(rows).toHaveLength(2)
    expect(rows[0].classes()).toContain('current')
    expect(wrapper.text()).toContain('30 min')
  })

  it("shows each method's outcome as a dot, failures marked", () => {
    const wrapper = mount(ExperimentGapList, { props: listProps() })
    const dots = wrapper.findAll('.gap-row')[0].findAll('.method-dot')

    expect(dots[0].classes()).toContain('ok')
    expect(dots[0].attributes('title')).toBe('VISTA: 2.10 km')
    expect(dots[1].classes()).toContain('failed')
  })

  it('emits the chosen size as a number and an emptied level as null', async () => {
    const wrapper = mount(ExperimentGapList, { props: listProps() })
    await wrapper.find('.size-select').setValue('4')
    await wrapper.find('.level-select').setValue('')

    expect(wrapper.emitted('update:size')).toEqual([[4]])
    expect(wrapper.emitted('update:level')).toEqual([[null]])
  })

  it('emits select', async () => {
    const wrapper = mount(ExperimentGapList, { props: listProps() })
    await wrapper.findAll('.gap-row')[1].trigger('click')

    expect(wrapper.emitted('select')).toEqual([['222_c2']])
  })

  it('says when the filters leave nothing', () => {
    const wrapper = mount(ExperimentGapList, { props: listProps({ gaps: [] }) })
    expect(wrapper.text()).toContain('No gap for these filters')
  })
})

describe('ExperimentGapDetail', () => {
  it('shows each method with its errors and cost', () => {
    const wrapper = mount(ExperimentGapDetail, { props: { detail: detailOf(), enabled: ['vista', 'hexa', 'linear'] } })

    expect(wrapper.text()).toContain('1.20 km')
    expect(wrapper.text()).toContain('640 tok')
    expect(wrapper.text()).toContain('28.3 min')
  })

  it('says why a method failed', () => {
    const wrapper = mount(ExperimentGapDetail, { props: { detail: detailOf(), enabled: [] } })
    expect(wrapper.find('.reason').text()).toBe('failed: no usable choice')
  })

  it('emits toggle-method', async () => {
    const wrapper = mount(ExperimentGapDetail, { props: { detail: detailOf(), enabled: ['vista'] } })
    const boxes = wrapper.findAll('.method-toggle')

    expect(boxes[0].element.checked).toBe(true)
    expect(boxes[1].element.checked).toBe(false)
    await boxes[1].trigger('change')
    expect(wrapper.emitted('toggle-method')).toEqual([['hexa']])
  })

  it("offers Hexa's other finished walks as an option, counting them without the kept one", async () => {
    const wrapper = mount(ExperimentGapDetail, { props: { detail: detailOf(), enabled: ['hexa'] } })
    const toggle = wrapper.find('.alternatives-toggle input')

    expect(wrapper.text()).toContain("Show Hexa's 1 other finished walk")
    expect(toggle.element.checked).toBe(false)
    await toggle.trigger('change')
    expect(wrapper.emitted('toggle-alternatives')).toBeTruthy()
  })

  it('names the methods whose cells are on the map', () => {
    const wrapper = mount(ExperimentGapDetail, { props: { detail: detailOf(), enabled: ['hexa', 'astar', 'linear'] } })
    expect(wrapper.find('.hint').text()).toContain('Hexa, A*')
    expect(wrapper.find('.hint').text()).not.toContain('Cell oracle')
  })
})

describe('ExperimentWalk', () => {
  it('sums up the exploration', () => {
    const wrapper = mount(ExperimentWalk, { props: { walk: walkOf() } })
    expect(wrapper.find('.walk-summary').text()).toContain('4 branches explored')
    expect(wrapper.find('.walk-summary').text()).toContain('1 out of steps')
    expect(wrapper.find('.walk-summary').text()).toContain('9 model calls')
  })

  it('lists each step of the kept path with its direction and reason', () => {
    const wrapper = mount(ExperimentWalk, { props: { walk: walkOf() } })
    const steps = wrapper.findAll('.step')

    expect(steps).toHaveLength(2)
    expect(steps[1].text()).toContain('NE')
    expect(steps[1].text()).toContain('direct to destination')
  })

  it("points the map at a step's cell while hovered", async () => {
    const wrapper = mount(ExperimentWalk, { props: { walk: walkOf() } })
    const step = wrapper.findAll('.step')[1]

    await step.trigger('mouseenter')
    await step.trigger('mouseleave')
    expect(wrapper.emitted('highlight-cell')).toEqual([[CELLS[1]], [null]])
  })

  it('draws one dot per branch end, coloured by how it ended', () => {
    const wrapper = mount(ExperimentWalk, { props: { walk: walkOf() } })
    const leaves = wrapper.findAll('circle.leaf')

    expect(leaves).toHaveLength(4)
    expect(leaves.map(l => l.classes().find(c => ['kept', 'finished', 'pruned', 'step_limit'].includes(c))).sort())
      .toEqual(['finished', 'kept', 'pruned', 'step_limit'])
    expect(wrapper.find('circle.pruned title').text()).toContain('Pruned')
  })

  it('draws the kept branch apart from the others', () => {
    const wrapper = mount(ExperimentWalk, { props: { walk: walkOf() } })
    expect(wrapper.findAll('path.edge.kept')).toHaveLength(2)
  })

  it("picks a branch to draw on the map, and a second click puts it away", async () => {
    const wrapper = mount(ExperimentWalk, { props: { walk: walkOf() } })
    const finished = wrapper.find('circle.finished')

    await finished.trigger('click')
    expect(wrapper.emitted('select-branch')[0]).toEqual([[CELLS[0], '871841442ffffff', '871841442ffffff']])
    expect(finished.classes()).toContain('selected')
    await finished.trigger('click')
    expect(wrapper.emitted('select-branch')[1]).toEqual([null])
  })

  it('says so when no branch reached the far end', () => {
    const walk = { ...walkOf(), steps: [] }
    const wrapper = mount(ExperimentWalk, { props: { walk } })
    expect(wrapper.text()).toContain('nothing was kept')
  })
})

describe('ExperimentVistaReasoning', () => {
  const mountWith = (overrides = {}) =>
    mount(ExperimentVistaReasoning, { props: { explanation: vistaExplanationOf(overrides) } })

  it("shows the chosen behaviour's attributes, the model's label first and its words on hover", () => {
    const chips = mountWith().findAll('.chip')

    expect(chips.map(c => c.text())).toEqual(['speed stable', 'course slight turn to the right', 'intent navigating', 'duration 13300~13350 s'])
    expect(chips[0].attributes('title')).toContain('consistent speed')
  })

  it('shows what supports the behaviour in the graph, with readable node names and weights', () => {
    const rows = mountWith().findAll('.support-row')

    expect(rows.map(r => r.find('.support-label').text())).toEqual(['chosen behaviour', 'navigation status: Under way using engine', 'length: [150, 200) m'])
    expect(rows[0].find('.support-bar span').attributes('style')).toContain('100%')
    expect(rows[2].find('.support-bar span').attributes('style')).toContain('20%')
  })

  it("falls back to the model's own words when its support is free text", () => {
    const behaviour = { ...vistaExplanationOf().behaviour, support: [], support_text: 'Highest weight for Cargo.' }
    const wrapper = mountWith({ behaviour })

    expect(wrapper.find('.support').exists()).toBe(false)
    expect(wrapper.find('details.more').text()).toContain('Highest weight for Cargo.')
  })

  it('shows the function chosen, its reasoning and its generated code', () => {
    const wrapper = mountWith()

    expect(wrapper.text()).toContain('Fits a stable speed.')
    expect(wrapper.find('.code-block pre').text()).toContain('def spatial_function')
  })

  it('shows the explanation and the regulatory rule', () => {
    const wrapper = mountWith()
    expect(wrapper.text()).toContain('Typical of a cargo vessel.')
    expect(wrapper.text()).toContain('Regulatory rule: Undetermined')
  })

  it('says plainly when VISTA settled on nothing', () => {
    const wrapper = mount(ExperimentVistaReasoning, {
      props: { explanation: { status: 'failed', behaviour: null, function: null, explanation: null } }
    })
    expect(wrapper.find('.failed-note').exists()).toBe(true)
    expect(wrapper.find('.chip').exists()).toBe(false)
  })
})

describe('ExperimentReasoning', () => {
  it("opens on Hexa's walk and switches to VISTA's reasoning", async () => {
    const wrapper = mount(ExperimentReasoning, { props: { walk: walkOf(), vista: vistaExplanationOf() } })

    expect(wrapper.findComponent(ExperimentWalk).exists()).toBe(true)
    await wrapper.findAll('.tab')[1].trigger('click')
    expect(wrapper.findComponent(ExperimentVistaReasoning).exists()).toBe(true)
    expect(wrapper.findComponent(ExperimentWalk).exists()).toBe(false)
  })

  it('only offers the methods that have a reasoning', () => {
    const wrapper = mount(ExperimentReasoning, { props: { walk: null, vista: vistaExplanationOf() } })

    expect(wrapper.findAll('.tab').map(t => t.text())).toEqual(['VISTA'])
    expect(wrapper.findComponent(ExperimentVistaReasoning).exists()).toBe(true)
  })

  it('keeps the chosen tab when another gap is opened', async () => {
    const wrapper = mount(ExperimentReasoning, { props: { walk: walkOf(), vista: vistaExplanationOf() } })
    await wrapper.findAll('.tab')[1].trigger('click')
    await wrapper.setProps({ walk: walkOf(), vista: vistaExplanationOf({ status: 'failed', behaviour: null, function: null, explanation: null }) })

    expect(wrapper.findComponent(ExperimentVistaReasoning).exists()).toBe(true)
  })

  it('passes the walk panel\'s pointers up', async () => {
    const wrapper = mount(ExperimentReasoning, { props: { walk: walkOf(), vista: null } })
    await wrapper.findAll('.step')[0].trigger('mouseenter')
    expect(wrapper.emitted('highlight-cell')).toEqual([['871841442ffffff']])
  })
})

describe('ExperimentResults', () => {
  const props = (overrides = {}) => {
    const o = overviewOf()
    return { size: 2, summary: o.summary, tests: o.tests, exports: o.exports,
      exportUrl: n => `/api/experiment/export/${n}.csv`, builtAt: o.results_built_at, canExportGaps: true, ...overrides }
  }

  it("shows only the selected size's rows, levels in order, the total last", () => {
    const wrapper = mount(ExperimentResults, { props: props() })
    const rows = wrapper.findAll('.summary tbody tr')

    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('facile')
    expect(rows[1].classes()).toContain('total')
    expect(rows[1].text()).toContain('[0.90; 1.50]')
  })

  it("shows the size's paired tests, a tiny p as <0.001", () => {
    const wrapper = mount(ExperimentResults, { props: props() })
    const rows = wrapper.findAll('.tests tbody tr')

    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('<0.001')
  })

  it('tells how to compute results that are missing', () => {
    const wrapper = mount(ExperimentResults, { props: props({ summary: null }) })
    expect(wrapper.text()).toContain('EGC27.metrics')
  })

  it('links the server tables for download and emits the gap export', async () => {
    const wrapper = mount(ExperimentResults, { props: props() })
    const links = wrapper.findAll('a.ghost-btn')

    expect(links.map(a => a.attributes('href'))).toEqual(['/api/experiment/export/summary.csv', '/api/experiment/export/tests.csv'])
    await wrapper.find('.export-gaps').trigger('click')
    expect(wrapper.emitted('export-gaps')).toBeTruthy()
  })
})

describe('ExperimentView', () => {
  const MapStub = { name: 'ExperimentMap' }

  it('loads the experiment and shows the first gap on the map', async () => {
    const wrapper = mount(ExperimentView, { props: { api: fakeApi() } })
    await flushPromises()

    expect(wrapper.findAll('.gap-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('111_c2')
    const map = wrapper.findComponent(MapStub)
    expect(map.props('layers').methods.features.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('Replay')
  })

  it('offers the base maps and passes a choice up to the app', async () => {
    const wrapper = mount(ExperimentView, { props: { api: fakeApi(), basemap: 'carto-dark' } })
    await flushPromises()

    const options = wrapper.findAll('.basemap-option')
    expect(options.length).toBeGreaterThan(1)
    await options.find(o => o.text() === 'Light').trigger('click')
    expect(wrapper.emitted('update:basemap')).toEqual([['carto-light']])
    await wrapper.find('.grayscale-toggle input').setValue(false)
    expect(wrapper.emitted('update:grayscale')).toEqual([[false]])
  })

  it("shows Hexa's reasoning for the selected gap", async () => {
    const wrapper = mount(ExperimentView, { props: { api: fakeApi() } })
    await flushPromises()

    expect(wrapper.findComponent(ExperimentWalk).exists()).toBe(true)
    await wrapper.findAll('.step')[0].trigger('mouseenter')
    const map = wrapper.findComponent(MapStub)
    expect(map.props('layers').highlight.features.map(f => f.properties.kind)).toEqual(['cell'])
  })

  it('shows why the view is unavailable', async () => {
    const wrapper = mount(ExperimentView, {
      props: { api: fakeApi({ failOverview: 'No experiment results found in EGC27/data' }) }
    })
    await flushPromises()

    expect(wrapper.find('.unavailable').text()).toContain('No experiment results')
  })
})
