import { createRouter, createWebHistory } from 'vue-router'
import ProntoPage from '@/pages/ProntoPage.vue'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [{ path: '/:pathMatch(.*)*', name: 'pronto', component: ProntoPage }],
})
