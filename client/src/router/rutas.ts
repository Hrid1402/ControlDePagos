import type { RouteRecordRaw } from 'vue-router'
export const rutas: RouteRecordRaw[] = [
  { path: '/', redirect: { name: 'login' } },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/AccesoPage.vue'),
    meta: { publica: true, titulo: 'Acceso' },
  },
  ...(['gerente', 'asistente'] as const).map((rol) => ({
    path: `/${rol}`,
    component: () => import('@/layouts/EspacioLayout.vue'),
    meta: { rol },
    children: [
      {
        path: '',
        name: `${rol}-inicio`,
        component: () => import('@/pages/InicioPage.vue'),
        meta: { titulo: 'Mi espacio' },
      },
    ],
  })),
  {
    path: '/:pathMatch(.*)*',
    name: 'no-encontrada',
    component: () => import('@/pages/AccesoPage.vue'),
    meta: { libre: true, titulo: 'Página no encontrada' },
  },
]
