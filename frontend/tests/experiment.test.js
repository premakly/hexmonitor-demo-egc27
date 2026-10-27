import { describe, expect, it } from 'vitest'

import { cellPolygon } from '../src/lib/geo.js'
import { gridDistance, latLngToCell } from 'h3-js'

import {
  GRID_MARGIN, branchCells, contextGrid, experimentLayers, formatKm, gapTableColumns, highlightLayer, layoutWalkTree, methodStyle, toCsv
} from '../src/lib/experiment.js'
import { CELLS, detailOf, gapOf, walkOf } from './experimentFixtures.js'

describe('methodStyle', () => {
  it('gives known methods a fixed label and colour', () => {
    expect(methodStyle('hexa')).toEqual({ label: 'Hexa', colour: '#f5a524' })
  })

  it('still styles a method it has never heard of', () => {
    const style = methodStyle('hexa_dense', 1)
    expect(style.label).toBe('hexa_dense')
    expect(style.colour).toMatch(/^#/)
  })
})

describe('formatKm', () => {
  it('shows a missing value as a dash, not NaN', () => {
    expect(formatKm(null)).toBe('—')
    expect(formatKm(NaN)).toBe('—')
    expect(formatKm(1.234)).toBe('1.23 km')
    expect(formatKm(17.08)).toBe('17.1 km')
  })
})

describe('experimentLayers', () => {
  it('is empty without a gap', () => {
    const layers = experimentLayers(null)
    expect(layers.methods.features).toEqual([])
  })

  it('keeps the gap out of the context track', () => {
    const { context } = experimentLayers(detailOf())
    const lats = context.features.filter(f => f.properties.kind === 'point').map(f => f.geometry.coordinates[1])
    expect(lats).not.toContain(46.04)
    expect(lats).toHaveLength(8)
  })

  it('draws the truth from anchor to anchor', () => {
    const { truth } = experimentLayers(detailOf())
    const line = truth.features.find(f => f.properties.kind === 'line').geometry.coordinates
    expect(line.map(c => c[1])).toEqual([46.03, 46.04, 46.05, 46.06])
  })

  it('draws each successful method between the same anchors, in its colour', () => {
    const { methods } = experimentLayers(detailOf())
    const hexa = methods.features.find(f => f.properties.method === 'hexa' && f.properties.kind === 'line')
    expect(hexa.properties.colour).toBe('#f5a524')
    expect(hexa.geometry.coordinates[0]).toEqual([-3, 46.03])
    expect(hexa.geometry.coordinates.at(-1)).toEqual([-3, 46.06])
  })

  it('draws nothing for a failed method', () => {
    const { methods } = experimentLayers(detailOf())
    expect(methods.features.some(f => f.properties.method === 'linear')).toBe(false)
  })

  it('leaves out the methods switched off', () => {
    const { methods, cells } = experimentLayers(detailOf(), ['vista'])
    expect(new Set(methods.features.map(f => f.properties.method))).toEqual(new Set(['vista']))
    expect(cells.features).toEqual([])
  })

  it('draws as boldest the very cells the line follows, not the first walk listed', () => {
    const { cells } = experimentLayers(detailOf())
    const kept = cells.features.filter(f => f.properties.method === 'hexa' && f.properties.rank === 0)
    expect(kept).toHaveLength(CELLS.length)
    expect(kept[0].geometry.type).toBe('Polygon')
    expect(kept[0].geometry.coordinates[0]).toEqual(cellPolygon(CELLS[0]))
  })

  it('draws the cells of every method that reports a path, each in its own colour', () => {
    const { cells } = experimentLayers(detailOf())
    const byMethod = m => cells.features.filter(f => f.properties.method === m)

    expect(byMethod('astar')).toHaveLength(3)
    expect(byMethod('astar')[0].properties.colour).toBe('#34d399')
    expect(byMethod('oracle')).toHaveLength(2)
    expect(byMethod('oracle')[0].properties.colour).toBe('#a78bfa')
    expect(byMethod('vista')).toEqual([])
  })

  it("hides a method's cells along with its line", () => {
    const { cells } = experimentLayers(detailOf(), ['hexa'])
    expect(new Set(cells.features.map(f => f.properties.method))).toEqual(new Set(['hexa']))
  })

  it('draws only the kept walk unless the others are asked for', () => {
    const { cells } = experimentLayers(detailOf())
    expect(cells.features.every(f => f.properties.rank === 0)).toBe(true)
  })

  it('draws the other finished walks fainter, on request, without repeating the kept one', () => {
    const { cells } = experimentLayers(detailOf(), null, ['hexa'], true)
    expect(cells.features.filter(f => f.properties.rank === 1)).toHaveLength(2)
    expect(cells.features.filter(f => f.properties.rank === 1).every(f => f.properties.method === 'hexa')).toBe(true)
    expect(cells.features.filter(f => f.properties.rank === 2)).toHaveLength(0)
  })

  it('draws no cells for a walk that failed', () => {
    const detail = detailOf()
    detail.methods[1] = { ...detail.methods[1], status: 'failed', path: null, points: [] }
    detail.methods[3] = { ...detail.methods[3], status: 'failed', points: [] }
    const methods = new Set(experimentLayers(detail).cells.features.map(f => f.properties.method))
    expect(methods.has('hexa')).toBe(false)
    expect(methods.has('astar')).toBe(false)
  })
})

describe('contextGrid', () => {
  const centreOf = feature => {
    const ring = feature.geometry.coordinates[0].slice(0, -1)
    const lon = ring.reduce((s, c) => s + c[0], 0) / ring.length
    const lat = ring.reduce((s, c) => s + c[1], 0) / ring.length
    return latLngToCell(lat, lon, 7)
  }

  it('covers both anchors and every gap cell, with rings to spare', () => {
    const detail = detailOf()
    const cells = new Set(contextGrid(detail).features.map(centreOf))
    const anchor = p => latLngToCell(p.lat, p.lon, 7)

    expect(cells.has(anchor(detail.track[3]))).toBe(true)
    expect(cells.has(anchor(detail.track[6]))).toBe(true)
    for (const c of detail.gap.cells) expect(cells.has(c)).toBe(true)
  })

  it('reaches GRID_MARGIN rings beyond the farther anchor', () => {
    const detail = detailOf()
    const features = contextGrid(detail).features
    const centre = centreOf(features.reduce((a, b) => (a.properties.fade > b.properties.fade ? a : b)))
    const farthest = Math.max(...features.map(f => gridDistance(centre, centreOf(f))))
    const anchorSpan = Math.max(...[detail.track[3], detail.track[6]].map(p => gridDistance(centre, latLngToCell(p.lat, p.lon, 7))))

    expect(farthest).toBe(anchorSpan + GRID_MARGIN)
  })

  it('fades from the centre to the rim', () => {
    const fades = contextGrid(detailOf()).features.map(f => f.properties.fade)
    expect(Math.max(...fades)).toBe(1)
    expect(Math.min(...fades)).toBeGreaterThan(0)
    expect(Math.min(...fades)).toBeLessThan(0.3)
  })

  it('is empty when the gap has no cells', () => {
    const detail = detailOf()
    detail.gap = { ...detail.gap, cells: [] }
    expect(contextGrid(detail).features).toEqual([])
  })

  it('is part of the layers of a gap', () => {
    expect(experimentLayers(detailOf()).grid.features.length).toBeGreaterThan(0)
    expect(experimentLayers(null).grid.features).toEqual([])
  })
})

describe('CSV export', () => {
  it('writes a header then one line per gap, a column per method and metric', () => {
    const csv = toCsv([gapOf('111_c2')], gapTableColumns(['vista', 'hexa']))
    const [head, row] = csv.trim().split('\n')
    expect(head).toContain('vista_mean_km')
    expect(head).toContain('hexa_status')
    expect(row).toContain('111_c2')
    expect(row).toContain('2.1')
    expect(row).toContain('failed')
  })

  it('quotes values that would break a CSV', () => {
    const csv = toCsv([{ a: 'x, "y"' }], [{ label: 'a', value: r => r.a }])
    expect(csv).toBe('a\n"x, ""y"""\n')
  })

  it('leaves missing values empty', () => {
    const csv = toCsv([{ a: null }], [{ label: 'a', value: r => r.a }])
    expect(csv).toBe('a\n\n')
  })
})

describe('layoutWalkTree', () => {
  const at = (layout, id) => layout.nodes.find(n => n.id === id)

  it('runs the kept branch along the top row', () => {
    const layout = layoutWalkTree(walkOf().tree)
    expect([0, 1, 2].map(id => at(layout, id).y)).toEqual([0, 0, 0])
  })

  it('gives every leaf its own row, the more probable branches nearer the top', () => {
    const layout = layoutWalkTree(walkOf().tree)
    expect([2, 3, 4, 5].map(id => at(layout, id).y)).toEqual([0, 1, 2, 3])
    expect(layout.rows).toBe(4)
  })

  it('places each node at its step, under its first child', () => {
    const layout = layoutWalkTree(walkOf().tree)
    expect(layout.nodes.map(n => n.x)).toEqual([0, 1, 2, 2, 1, 1])
    expect(layout.depth).toBe(2)
  })

  it('marks the edges leading to the kept answer', () => {
    const kept = layoutWalkTree(walkOf().tree).edges.filter(e => e.onKept).map(e => e.to.id)
    expect(kept.sort()).toEqual([1, 2])
  })

  it('is empty without a tree', () => {
    expect(layoutWalkTree(null)).toEqual({ nodes: [], edges: [], rows: 0, depth: 0 })
  })
})

describe('branchCells', () => {
  it('lists the cells from the start to a node', () => {
    expect(branchCells(walkOf().tree, 2)).toEqual([CELLS[0], '871841442ffffff', CELLS[1]])
    expect(branchCells(walkOf().tree, 0)).toEqual([CELLS[0]])
  })
})

describe('highlightLayer', () => {
  it('outlines a hovered cell', () => {
    const { features } = highlightLayer(CELLS[0])
    expect(features.map(f => f.properties.kind)).toEqual(['cell'])
  })

  it("draws a picked branch's cells and the line through them", () => {
    const kinds = highlightLayer(null, CELLS).features.map(f => f.properties.kind)
    expect(kinds).toEqual(['branch', 'branch', 'branch-line'])
  })

  it('is empty when nothing is pointed at', () => {
    expect(highlightLayer().features).toEqual([])
  })
})
