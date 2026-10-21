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
        {
          path: '/revision/limites',
          name: 'revision-limites',
          component: () => import('@/pages/LimitesRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión de límites' },
        },
        {
          path: '/revision/servicios',
          name: 'revision-servicios',
          component: () => import('@/pages/ServiciosRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión de servicios' },
        },
        {
          path: '/revision/deudas',
          name: 'revision-deudas',
          component: () => import('@/pages/DeudasRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión de la lista de deudas' },
        },
        {
          path: '/revision/detalle-deuda',
          name: 'revision-detalle-deuda',
          component: () => import('@/pages/DeudaDetalleRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión del detalle de deuda' },
        },
        {
          path: '/revision/bandeja',
          name: 'revision-bandeja',
          component: () => import('@/pages/BandejaRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión de la bandeja' },
        },
        {
          path: '/revision/deuda',
          name: 'revision-deuda',
          component: () => import('@/pages/DeudaRevisionPage.vue'),
          meta: { libre: true, titulo: 'Revisión del formulario de deuda' },
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
      {
        path: 'deudas/:id',
        name: `${rol}-deuda`,
        component: () => import('@/pages/DeudaDetallePage.vue'),
        meta: { titulo: 'Deuda' },
      },
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
