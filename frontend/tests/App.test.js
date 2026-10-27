import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import App from '../src/App.vue'
import { DEMO_DEFAULTS } from '../src/demo.config.js'
import { createApi } from '../src/lib/api.js'
import { fakeApi } from './experimentFixtures.js'

vi.mock('../src/components/ExperimentMap.vue', () => ({
  default: { name: 'ExperimentMap', props: ['basemap', 'grayscale', 'layers', 'fit'], template: '<div></div>' }
}))

describe('App', () => {
  it('is the demo and nothing else: its title, then the experiment view', async () => {
    const wrapper = mount(App, { props: { api: fakeApi() } })
    await flushPromises()

    expect(wrapper.find('.brand-name').text()).toBe('Demo EGC27')
    expect(wrapper.find('.view-switch').exists()).toBe(false)
    expect(wrapper.findAll('.gap-row')).toHaveLength(2)
  })

  it('arrives on the satellite base map, in greys, whatever was chosen on a previous visit', async () => {
    const first = mount(App, { props: { api: fakeApi() } })
    await flushPromises()
    await first.findAll('.basemap-option').find(o => o.text() === 'Light').trigger('click')
    expect(first.vm.basemap).toBe('carto-light')

    const again = mount(App, { props: { api: fakeApi() } })
    expect(again.vm.basemap).toBe('esri-satellite')
    expect(again.vm.grayscale).toBe(true)
  })

  it('opens the configured vessel on arrival', async () => {
    const wrapper = mount(App, { props: { api: fakeApi(), defaults: { ...DEMO_DEFAULTS, vessel: 222 } } })
    await flushPromises()

    expect(wrapper.find('.gap-row.current').text()).toContain('222')
  })

  it('opens the configured gap size when there is one', async () => {
    const wrapper = mount(App, { props: { api: fakeApi(), defaults: { ...DEMO_DEFAULTS, vessel: 111, size: 4 } } })
    await flushPromises()

    expect(wrapper.find('.size-select').element.value).toBe('4')
    expect(wrapper.find('.gap-row.current').text()).toContain('111')
  })

  it('falls back to the first gap when the configured vessel is not in the data', async () => {
    const wrapper = mount(App, { props: { api: fakeApi(), defaults: { ...DEMO_DEFAULTS, vessel: 999, size: 8 } } })
    await flushPromises()

    expect(wrapper.find('.size-select').element.value).toBe('2')
    expect(wrapper.find('.gap-row.current').text()).toContain('111')
  })

  it('ships with the satellite base map in greys and vessel 538009058', () => {
    expect(DEMO_DEFAULTS).toMatchObject({ basemap: 'esri-satellite', grayscale: true, vessel: 538009058 })
  })
})

describe('api', () => {
  it('asks the experiment endpoints, dropping empty filters', async () => {
    const calls = []
    const api = createApi('/api', async url => {
      calls.push(url)
      return { ok: true, json: async () => ({ gaps: [] }) }
    })
    await api.experimentGaps({ size: 4, level: null })
    await api.experimentGap('111 c4')

    expect(calls).toEqual(['/api/experiment/gaps?size=4', '/api/experiment/gaps/111%20c4'])
    expect(api.experimentExportUrl('summary')).toBe('/api/experiment/export/summary.csv')
  })

  it("reports the backend's own explanation of an error", async () => {
    const api = createApi('/api', async () => ({ ok: false, status: 404, json: async () => ({ detail: 'no such gap: x' }) }))
    await expect(api.experimentGap('x')).rejects.toThrow('no such gap: x')
  })

  it('says when the backend cannot be reached', async () => {
    const api = createApi('/api', async () => { throw new TypeError('fetch failed') })
    await expect(api.experiment()).rejects.toMatchObject({ status: 0 })
  })
})
