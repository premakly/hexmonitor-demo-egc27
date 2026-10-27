import { cellToBoundary, cellToLatLng } from 'h3-js'

// The sphere radius the backend uses for its distance test, so the outline is
// drawn where the cells are actually cut.
export const EARTH_RADIUS_KM = 6371

export function emptyCollection() {
  return { type: 'FeatureCollection', features: [] }
}

// The outline of a circle: points at one great-circle radius from the centre.
export function circlePolygon(lon, lat, radiusKm, steps = 96) {
  const toRad = Math.PI / 180
  const angular = radiusKm / EARTH_RADIUS_KM
  const phi1 = lat * toRad
  const lambda1 = lon * toRad

  const ring = []
  for (let i = 0; i < steps; i++) {
    const bearing = (i / steps) * 2 * Math.PI
    const phi2 = Math.asin(
      Math.sin(phi1) * Math.cos(angular) +
        Math.cos(phi1) * Math.sin(angular) * Math.cos(bearing)
    )
    const lambda2 =
      lambda1 +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angular) * Math.cos(phi1),
        Math.cos(angular) - Math.sin(phi1) * Math.sin(phi2)
      )
    ring.push([((lambda2 / toRad + 540) % 360) - 180, phi2 / toRad])
  }
  ring.push(ring[0]) // a GeoJSON ring must close exactly
  return ring
}

export function circleCollection(centre, radiusKm) {
  if (!centre) return emptyCollection()
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'Polygon', coordinates: [circlePolygon(centre.lon, centre.lat, radiusKm)] }
  }
}

export function centreCollection(centre) {
  if (!centre) return emptyCollection()
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'Point', coordinates: [centre.lon, centre.lat] }
  }
}

// [[west, south], [east, north]] of every coordinate in a collection, or null
// when there is none. Walks nested rings so it serves polygons and lines alike.
export function boundsOf(collection) {
  let west = 180
  let east = -180
  let south = 90
  let north = -90
  let seen = false

  const visit = coords => {
    if (typeof coords[0] === 'number') {
      const [lon, lat] = coords
      if (lon < west) west = lon
      if (lon > east) east = lon
      if (lat < south) south = lat
      if (lat > north) north = lat
      seen = true
      return
    }
    for (const inner of coords) visit(inner)
  }

  for (const feature of (collection && collection.features) || []) {
    if (feature.geometry && feature.geometry.coordinates) visit(feature.geometry.coordinates)
  }
  return seen ? [[west, south], [east, north]] : null
}

// A path of H3 cells as a line through their centres: consistent with the
// density layer's own grid rather than the raw AIS points either side of a gap.
export function cellsToLine(cells) {
  return cells.map(cell => {
    const [lat, lon] = cellToLatLng(cell)
    return [lon, lat]
  })
}

// One H3 cell as a closed GeoJSON ring of [lon, lat] — the same hexagon the
// density layer draws for that cell, so a completed path lines up with it.
export function cellPolygon(cell) {
  const ring = cellToBoundary(cell).map(([lat, lon]) => [lon, lat])
  ring.push(ring[0])
  return ring
}

export function statsOf(collection) {
  // A plain loop: Math.max(...values) throws a RangeError above ~200 000
  // arguments, which a large dataset reaches.
  let points = 0
  let highest = 0
  for (const f of collection.features) {
    const count = f.properties.count
    points += count
    if (count > highest) highest = count
  }
  return { cells: collection.features.length, points, max: highest }
}
