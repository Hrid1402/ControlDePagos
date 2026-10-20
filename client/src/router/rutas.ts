import type { RouteRecordRaw } from 'vue-router'
export const rutas: RouteRecordRaw[] = [
  { path: '/login', redirect: (to) => ({ name: 'login', query: to.query, hash: to.hash }) },
  ...(import.meta.env.DEV
    ? [{ path: '/revision/acceso', redirect: { name: 'login', query: { revision: '1' } } }]
    : []),
  {
    path: '/',
    name: 'login',
    component: () => import('@/pages/AccesoPage.vue'),
    meta: { publica: true, titulo: 'Acceso' },
  },
  ...(['recuperar', 'restablecer', 'sin-permiso'] as const).map((nombre) => ({
    path: nombre === 'restablecer' ? '/restablecer/:token?' : `/${nombre}`,
    name: nombre,
    component: () => import('@/pages/AccesoPage.vue'),
    meta:
      nombre === 'sin-permiso'
        ? { libre: true, titulo: 'Sin acceso' }
        : nombre === 'restablecer'
          ? // El enlace del correo debe abrirse aunque haya otra sesión abierta.
            { libre: true, titulo: 'Nueva contraseña' }
          : { publica: true, titulo: 'Recuperar acceso' },
  })),
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
