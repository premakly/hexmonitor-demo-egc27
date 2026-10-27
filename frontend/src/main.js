import { createApp } from 'vue'

import App from './App.vue'
import { createApi } from './lib/api.js'
import { createStaticApi } from './lib/staticApi.js'
import './styles/theme.css'

// Built with VITE_STATIC=1 (GitHub Pages), the demo reads its exported files;
// otherwise it asks the backend.
const api = import.meta.env.VITE_STATIC === '1' ? createStaticApi() : createApi()

createApp(App, { api }).mount('#app')
