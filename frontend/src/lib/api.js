// The demo's backend, as functions: the read-only experiment endpoints.

export class ApiError extends Error {
  constructor(status, message, detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0 when the backend could not be reached at all
    this.detail = detail
  }
}

function messageFrom(status, detail) {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.message === 'string') return detail.message
  if (Array.isArray(detail)) {
    return detail
      .map(d => (d.loc && d.loc.length > 1 ? `${d.loc.slice(1).join('.')}: ${d.msg}` : d.msg))
      .join('; ')
  }
  return `The backend answered HTTP ${status}.`
}

function queryString(params) {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params || {})) {
    if (value === null || value === undefined || value === '') continue
    qs.set(key, value)
  }
  const text = qs.toString()
  return text ? `?${text}` : ''
}

export function createApi(baseUrl = '/api', fetchImpl = null) {
  const send = (...args) => (fetchImpl || globalThis.fetch)(...args)

  async function request(path, { params, signal } = {}) {
    let response
    try {
      response = await send(`${baseUrl}${path}${queryString(params)}`, { signal })
    } catch (e) {
      if (e && e.name === 'AbortError') throw e
      throw new ApiError(0, `Cannot reach the backend: ${e.message}`)
    }
    if (!response.ok) {
      let detail = null
      try {
        detail = (await response.json()).detail
      } catch (e) {
        // an error without a JSON body: the status alone will do
      }
      throw new ApiError(response.status, messageFrom(response.status, detail), detail)
    }
    return response.json()
  }

  return {
    request,
    experiment: () => request('/experiment'),
    experimentGaps: params => request('/experiment/gaps', { params }),
    experimentGap: id => request(`/experiment/gaps/${encodeURIComponent(id)}`),
    // A plain link, not a fetch: the browser downloads the file itself.
    experimentExportUrl: name => `${baseUrl}/experiment/export/${name}.csv`
  }
}
