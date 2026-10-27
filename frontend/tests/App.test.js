import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import App from '../src/App.vue'
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

  it('remembers the base map chosen, in this browser', async () => {
    const wrapper = mount(App, { props: { api: fakeApi() } })
    await flushPromises()
    await wrapper.findAll('.basemap-option').find(o => o.text() === 'Light').trigger('click')

    expect(wrapper.vm.basemap).toBe('carto-light')
    expect(mount(App, { props: { api: fakeApi() } }).vm.basemap).toBe('carto-light')
  })

  it('falls back to the default base map when the remembered one is unknown', () => {
    localStorage.setItem('egc27demo.basemap', JSON.stringify('gone'))
    expect(mount(App, { props: { api: fakeApi() } }).vm.basemap).toBe('carto-dark')
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
