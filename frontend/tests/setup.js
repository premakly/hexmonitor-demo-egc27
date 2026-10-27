import { afterEach } from 'vitest'

// Preferences are kept in localStorage; a test must never see another's.
afterEach(() => {
  localStorage.clear()
})
