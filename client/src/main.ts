import { createApp } from 'vue'
import { createPinia } from 'pinia'

import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import 'primeicons/primeicons.css'
import './assets/main.css'
import { configuracionUi } from './config/ui'

import App from './App.vue'
import router from './router'
import { useSesionStore } from './stores/sesion'
import { http } from './api/http'
import { crearControlSesion, controlSesionKey } from './services/controlSesion'
import { instalarAcceso } from './router/guard'

const app = createApp(App)

app.use(createPinia())
const control = crearControlSesion(useSesionStore(), http)
app.provide(controlSesionKey, control)
const quitarAcceso = instalarAcceso(router, control)
control.iniciar()
app.use(router)
if (import.meta.hot)
  import.meta.hot.dispose(() => {
    control.detener()
    quitarAcceso()
  })
app.use(PrimeVue, configuracionUi)
app.use(ToastService)
app.use(ConfirmationService)

app.mount('#app')
