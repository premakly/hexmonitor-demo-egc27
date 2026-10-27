// The Experiment view's data work, kept out of the components so it can be
// tested without a map: method colours and labels, the map layers of one gap,
// and the CSV export of a table.

import { getResolution, gridDisk, gridDistance, latLngToCell } from 'h3-js'

import { cellPolygon, cellsToLine, emptyCollection } from './geo.js'

// Rings of context cells drawn beyond the gap on every side.
export const GRID_MARGIN = 3

// One colour per method. Hexa keeps the app's accent (the colour of a walked
// path everywhere else in Hex Monitor); the others are chosen to stay apart
// on both dark and light base maps.
const KNOWN = {
  vista: { label: 'VISTA', colour: '#60a5fa' },
  hexa: { label: 'Hexa', colour: '#f5a524' },
  linear: { label: 'Linear', colour: '#9ca3af' },
  astar: { label: 'A*', colour: '#34d399' },
  oracle: { label: 'Cell oracle', colour: '#a78bfa' },
  oracle_lisse: { label: 'Smoothed oracle', colour: '#f472b6' }
}
const FALLBACK = ['#22d3ee', '#fb7185', '#facc15', '#c084fc']

export function methodStyle(method, index = 0) {
  return KNOWN[method] || { label: method, colour: FALLBACK[index % FALLBACK.length] }
}

export const methodLabel = method => methodStyle(method).label

export function formatKm(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value < 10 ? `${value.toFixed(2)} km` : `${value.toFixed(1)} km`
}

const coord = p => [p.lon, p.lat]

function line(coords, properties) {
  return { type: 'Feature', properties, geometry: { type: 'LineString', coordinates: coords } }
}

function point(p, properties) {
  return { type: 'Feature', properties, geometry: { type: 'Point', coordinates: coord(p) } }
}

// The H3 grid around a gap, as a faint backdrop: a disc of cells centred
// between the two anchors, wide enough to hold both plus GRID_MARGIN rings.
// Each cell carries `fade`, 1 at the centre down to near 0 at the rim, so the
// grid dissolves outward like a circle of context instead of ending on a
// hard edge.
export function contextGrid(detail, margin = GRID_MARGIN) {
  const cells = (detail && detail.gap && detail.gap.cells) || []
  if (!cells.length) return emptyCollection()
  const { before, after } = anchors(detail)
  if (!before || !after) return emptyCollection()

  const resolution = getResolution(cells[0])
  const from = latLngToCell(before.lat, before.lon, resolution)
  const to = latLngToCell(after.lat, after.lon, resolution)
  const centre = latLngToCell((before.lat + after.lat) / 2, (before.lon + after.lon) / 2, resolution)
  let span
  try {
    span = Math.max(gridDistance(centre, from), gridDistance(centre, to))
  } catch (e) {
    span = Math.ceil(cells.length / 2) + 1 // across a pentagon gridDistance has no answer
  }
  const radius = span + margin

  return {
    type: 'FeatureCollection',
    features: gridDisk(centre, radius).map(cell => {
      let ring
      try {
        ring = gridDistance(centre, cell)
      } catch (e) {
        ring = radius
      }
      return {
        type: 'Feature',
        properties: { fade: Math.max(0, 1 - ring / (radius + 1)) },
        geometry: { type: 'Polygon', coordinates: [cellPolygon(cell)] }
      }
    })
  }
}

function anchors(detail) {
  const { idx_start: start, idx_end: end } = detail.gap
  const before = detail.track.find(p => p.idx === start - 1)
  const after = detail.track.find(p => p.idx === end + 1)
  return { before, after }
}

// Everything drawn for one gap, as GeoJSON collections:
//  - context: the known window around the gap (line and its AIS points);
//  - truth:   the real track through the gap, anchors included;
//  - methods: one line (anchors included) and its points per enabled method
//             that produced a completion;
//  - cells:   the cells each cell-based method went through (Hexa, A*, the
//             oracles: any method that reports a path), in its own colour: the
//             path it kept (rank 0, the one its line follows) and, if
//             `alternatives` is asked for, its other finished walks (Hexa only
//             has some). `cellsOf` restricts this to a list of methods; null
//             means every method with a path. Nothing for a failed method.
export function experimentLayers(detail, enabled = null, cellsOf = null, alternatives = false) {
  if (!detail) {
    return { grid: emptyCollection(), context: emptyCollection(), truth: emptyCollection(), methods: emptyCollection(), cells: emptyCollection() }
  }
  const { idx_start: start, idx_end: end } = detail.gap
  const { before, after } = anchors(detail)
  const isOn = m => enabled === null || enabled.includes(m)

  const left = detail.track.filter(p => p.idx < start)
  const right = detail.track.filter(p => p.idx > end)
  const context = {
    type: 'FeatureCollection',
    features: [
      ...[left, right].filter(part => part.length > 1).map(part => line(part.map(coord), { kind: 'line' })),
      ...[...left, ...right].map(p => point(p, { kind: 'point' }))
    ]
  }

  const truthPath = [before, ...detail.truth, after].filter(Boolean)
  const truth = {
    type: 'FeatureCollection',
    features: [
      line(truthPath.map(coord), { kind: 'line' }),
      ...detail.truth.map(p => point(p, { kind: 'point' }))
    ]
  }

  const methodFeatures = []
  const cellFeatures = []
  detail.methods.forEach((m, i) => {
    if (!isOn(m.method)) return
    const { colour } = methodStyle(m.method, i)
    if (m.status === 'ok' && m.points.length) {
      const path = [before, ...m.points, after].filter(Boolean)
      methodFeatures.push(line(path.map(coord), { kind: 'line', method: m.method, colour }))
      m.points.forEach(p => methodFeatures.push(point(p, { kind: 'point', method: m.method, colour })))
    }
    const drawsCells = cellsOf === null ? Boolean(m.path && m.path.length) : cellsOf.includes(m.method)
    if (drawsCells && m.status === 'ok') {
      // Rank 0 is the walk the method kept: the one its line is drawn along.
      // The other finished walks follow, fainter, without repeating it.
      const same = cells => JSON.stringify(cells) === JSON.stringify(m.path)
      const others = alternatives
        ? (m.alternatives || []).map(a => a.path).filter(cells => cells && !same(cells))
        : []
      const walks = [m.path, ...others].filter(Boolean)
      walks.forEach((cells, rank) => {
        for (const cell of cells || []) {
          cellFeatures.push({
            type: 'Feature',
            properties: { method: m.method, colour, rank },
            geometry: { type: 'Polygon', coordinates: [cellPolygon(cell)] }
          })
        }
      })
    }
  })

  return {
    grid: contextGrid(detail),
    context,
    truth,
    methods: { type: 'FeatureCollection', features: methodFeatures },
    cells: { type: 'FeatureCollection', features: cellFeatures }
  }
}

// A table as CSV text: a header of column labels, then one line per row.
// Values with a comma, a quote or a line break are quoted.
export function toCsv(rows, columns) {
  const escape = value => {
    if (value === null || value === undefined) return ''
    const text = String(value)
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  const head = columns.map(c => escape(c.label)).join(',')
  const body = rows.map(r => columns.map(c => escape(c.value(r))).join(','))
  return [head, ...body].join('\n') + '\n'
}

// The per-gap table, flattened to one column per method and metric, for export.
export function gapTableColumns(methods) {
  const columns = [
    { label: 'gap_id', value: g => g.gap_id },
    { label: 'mmsi', value: g => g.mmsi },
    { label: 'level', value: g => g.level },
    { label: 'size_cells', value: g => g.size_cells },
    { label: 'duration_h', value: g => g.duration_h },
    { label: 'length_km', value: g => g.length_km }
  ]
  for (const m of methods) {
    columns.push({ label: `${m}_status`, value: g => g.methods[m]?.status })
    columns.push({ label: `${m}_mean_km`, value: g => g.methods[m]?.mean_km })
    columns.push({ label: `${m}_frechet_km`, value: g => g.methods[m]?.frechet_km })
  }
  return columns
}

// ------------------------------------------------------------ explaining a walk

// Hexa's exploration as a drawable tree (a dendrogram read left to right):
// x is the step, y the row of a branch. Children are ordered so the branch
// leading to the kept answer comes first, then by their best leaf's
// probability: the kept path runs along the top row, and the closer a branch
// is to it, the more the walk believed in it. A parent sits on its first
// child's row, so every branch is a straight run until it splits off.
export function layoutWalkTree(tree) {
  const nodes = (tree && tree.nodes) || []
  if (!nodes.length) return { nodes: [], edges: [], rows: 0, depth: 0 }

  const children = new Map(nodes.map(n => [n.id, []]))
  for (const n of nodes) if (n.parent !== null && n.parent !== undefined) children.get(n.parent).push(n.id)

  const best = new Map()
  const leadsToKept = new Map()
  const visit = id => {
    const node = nodes[id]
    let top = node.probability ?? -1
    let kept = node.outcome === 'kept'
    for (const c of children.get(id)) {
      visit(c)
      top = Math.max(top, best.get(c))
      kept = kept || leadsToKept.get(c)
    }
    best.set(id, top)
    leadsToKept.set(id, kept)
  }
  const roots = nodes.filter(n => n.parent === null || n.parent === undefined).map(n => n.id)
  roots.forEach(visit)

  const order = ids => [...ids].sort((a, b) =>
    (leadsToKept.get(b) - leadsToKept.get(a)) || (best.get(b) - best.get(a)) || (a - b))

  const row = new Map()
  let next = 0
  const place = id => {
    const kids = order(children.get(id))
    if (!kids.length) {
      row.set(id, next++)
      return
    }
    kids.forEach(place)
    row.set(id, row.get(kids[0]))
  }
  order(roots).forEach(place)

  const placed = nodes.map(n => ({ ...n, x: n.depth, y: row.get(n.id), onKept: leadsToKept.get(n.id) }))
  const edges = placed
    .filter(n => n.parent !== null && n.parent !== undefined)
    .map(n => ({ from: placed[n.parent], to: n, onKept: n.onKept }))
  return { nodes: placed, edges, rows: next, depth: Math.max(...nodes.map(n => n.depth)) }
}

// The cells from the walk's start to a node of its tree, in order.
export function branchCells(tree, nodeId) {
  const nodes = (tree && tree.nodes) || []
  const cells = []
  for (let n = nodes[nodeId]; n; n = n.parent === null || n.parent === undefined ? null : nodes[n.parent]) {
    cells.unshift(n.cell)
  }
  return cells
}

// What is highlighted on the map from the walk panel: one hovered cell, and
// one branch picked in the tree (its cells and a line through their centres).
export function highlightLayer(cell = null, branch = null) {
  const features = []
  for (const c of branch || []) {
    features.push({ type: 'Feature', properties: { kind: 'branch' }, geometry: { type: 'Polygon', coordinates: [cellPolygon(c)] } })
  }
  if (branch && branch.length > 1) {
    features.push(line(cellsToLine(branch), { kind: 'branch-line' }))
  }
  if (cell) {
    features.push({ type: 'Feature', properties: { kind: 'cell' }, geometry: { type: 'Polygon', coordinates: [cellPolygon(cell)] } })
  }
  return { type: 'FeatureCollection', features }
}
