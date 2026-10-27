// The demo's data as static files (see backend/egc27demo/export_static.py),
// for hosting without a server, on GitHub Pages. Same interface as
// createApi(): the rest of the interface cannot tell the two apart.

import { ApiError } from './api.js'

const NOT_EXPORTED =
  'The demo data are missing from this build: export them with ' +
  '`python -m egc27demo.export_static` before building.'

export function createStaticApi(baseUrl = `${import.meta.env.BASE_URL}data`, fetchImpl = null) {
  const send = (...args) => (fetchImpl || globalThis.fetch)(...args)

  async function load(path, missing) {
    let response
    try {
      response = await send(`${baseUrl}/${path}`)
    } catch (e) {
      throw new ApiError(0, `Cannot load the demo data: ${e.message}`)
    }
    if (!response.ok) throw new ApiError(response.status, response.status === 404 ? missing : `HTTP ${response.status} for ${path}`)
    return response.json()
  }

  // Every gap is in one file, read once: filters are applied here, as the
  // backend would.
  let allGaps = null
  function gaps() {
    if (!allGaps) {
      allGaps = load('gaps.json', NOT_EXPORTED).catch(e => {
        allGaps = null // a failed read may succeed when tried again
        throw e
      })
    }
    return allGaps
  }

  return {
    experiment: () => load('overview.json', NOT_EXPORTED),
    experimentGaps: async ({ size = null, level = null } = {}) => {
      const { gaps: rows } = await gaps()
      return {
        gaps: rows.filter(g =>
          (size === null || size === undefined || g.size_cells === Number(size)) &&
          (!level || g.level === level))
      }
    },
    experimentGap: id => load(`gaps/${encodeURIComponent(encodeURIComponent(id))}.json`, `no such gap: ${id}`),
    experimentExportUrl: name => `${baseUrl}/export/${name}.csv`
  }
}
