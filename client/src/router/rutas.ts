import type { RouteRecordRaw } from 'vue-router'
import { CUENTA, SECCIONES, nombreRuta } from '@/config/navegacion'

export const rutas: RouteRecordRaw[] = [
  { path: '/login', redirect: (to) => ({ name: 'login', query: to.query, hash: to.hash }) },
  ...(import.meta.env.DEV
    ? [
        { path: '/revision/acceso', redirect: { name: 'login', query: { revision: '1' } } },
        {
          path: '/revision/calendario',
          name: 'revision-calendario',
          component: () => import('@/pages/CalendarioRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión de calendario' },
        },
      ]
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
      ...SECCIONES[rol].map((seccion) => ({
        path: seccion.clave,
        name: nombreRuta(rol, seccion.clave),
        component: seccion.pagina ?? (() => import('@/pages/SeccionPendientePage.vue')),
        meta: { titulo: seccion.etiqueta },
      })),
      ...(rol === 'gerente'
        ? [
            {
              path: 'asistentes/:id',
              name: 'gerente-asistente',
              component: () => import('@/pages/AsistenteDetallePage.vue'),
              meta: { titulo: 'Asistente' },
            },
          ]
        : []),
      {
        path: CUENTA,
        name: nombreRuta(rol, CUENTA),
        component: () => import('@/pages/MiCuentaPage.vue'),
        meta: { titulo: 'Mi cuenta' },
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
