import { createRouter, createWebHistory } from 'vue-router'
import { rutas } from './rutas'
export default createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes: rutas })
