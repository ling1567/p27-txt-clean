import { createApp } from 'vue'
import VueDiff from 'vue-diff'
import 'vue-diff/dist/index.css'
import './style.css'
import App from './App.vue'

const app = createApp(App)
app.use(VueDiff)
app.mount('#app')
