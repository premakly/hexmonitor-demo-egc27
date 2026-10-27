import { describe, expect, it } from 'vitest'

import { createStaticApi } from '../src/lib/staticApi.js'

const FILES = {
  '/demo/data/overview.json': { sizes: [2, 4], methods: ['hexa'] },
  '/demo/data/gaps.json': {
    gaps: [
      { gap_id: '111_c2', size_cells: 2, level: 'facile' },
      { gap_id: '222_c2', size_cells: 2, level: 'difficile' },
      { gap_id: '111_c4', size_cells: 4, level: 'facile' }
    ]
  },
  '/demo/data/gaps/111_c2.json': { gap: { gap_id: '111_c2' } },
  '/demo/data/gaps/a%252Fb.json': { gap: { gap_id: 'a/b' } }
}

function fakeFetch(calls = []) {
  return async url => {
    calls.push(url)
    if (!(url in FILES)) return { ok: false, status: 404, json: async () => ({}) }
    return { ok: true, status: 200, json: async () => FILES[url] }
  }
}

describe('createStaticApi', () => {
  it('reads the overview from its file', async () => {
    const api = createStaticApi('/demo/data', fakeFetch())
    expect((await api.experiment()).sizes).toEqual([2, 4])
  })

  it('filters the gaps by size and level, as the backend does', async () => {
    const api = createStaticApi('/demo/data', fakeFetch())

    expect((await api.experimentGaps({ size: 2 })).gaps.map(g => g.gap_id)).toEqual(['111_c2', '222_c2'])
    expect((await api.experimentGaps({ size: 2, level: 'difficile' })).gaps.map(g => g.gap_id)).toEqual(['222_c2'])
    expect((await api.experimentGaps({ size: '4', level: null })).gaps.map(g => g.gap_id)).toEqual(['111_c4'])
    expect((await api.experimentGaps()).gaps).toHaveLength(3)
  })

  it('reads the gap list once, however often it is filtered', async () => {
    const calls = []
    const api = createStaticApi('/demo/data', fakeFetch(calls))
    await api.experimentGaps({ size: 2 })
    await api.experimentGaps({ size: 4 })

    expect(calls.filter(u => u.endsWith('gaps.json'))).toHaveLength(1)
  })

  it('opens one gap from its own file, its id escaped as the export named it', async () => {
    const api = createStaticApi('/demo/data', fakeFetch())

    expect((await api.experimentGap('111_c2')).gap.gap_id).toBe('111_c2')
    expect((await api.experimentGap('a/b')).gap.gap_id).toBe('a/b')
  })

  it('reports an unknown gap as the backend would', async () => {
    const api = createStaticApi('/demo/data', fakeFetch())
    await expect(api.experimentGap('nope')).rejects.toMatchObject({ status: 404, message: 'no such gap: nope' })
  })

  it('says how to fix a build without its data', async () => {
    const api = createStaticApi('/elsewhere', fakeFetch())
    await expect(api.experiment()).rejects.toThrow('export_static')
  })

  it('tries the gap list again after a failed read', async () => {
    let fail = true
    const api = createStaticApi('/demo/data', async url => {
      if (fail) throw new TypeError('offline')
      return fakeFetch()(url)
    })
    await expect(api.experimentGaps({ size: 2 })).rejects.toMatchObject({ status: 0 })
    fail = false
    expect((await api.experimentGaps({ size: 2 })).gaps).toHaveLength(2)
  })

  it('links the tables as files beside the data', () => {
    const api = createStaticApi('/demo/data', fakeFetch())
    expect(api.experimentExportUrl('summary')).toBe('/demo/data/export/summary.csv')
  })
})
