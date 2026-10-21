import type { Component } from 'vue'
import type { Rol } from '@/types/api'

/** Una sección del espacio de un rol. La clave vacía es la sección de inicio del rol. */
export interface Seccion {
  clave: string
  etiqueta: string
  descripcion: string
  /** Va en las pestañas de la hoja; las demás, en «Más» (en celular se muestran todas). */
  principal: boolean
  /** Pantalla de la sección; sin ella, la ruta muestra que la sección está pendiente. */
  pagina?: () => Promise<Component>
}

// Fuente única de las rutas y de las pestañas: una sección nueva se agrega aquí y obtiene su ruta
// protegida por rol. Mientras su historia no tenga pantalla, la ruta muestra que está pendiente.
export const SECCIONES: Record<Rol, Seccion[]> = {
  gerente: [
    {
      clave: '',
      etiqueta: 'Panel',
      descripcion: 'Lo pagado, lo pendiente y lo que necesita tu atención este mes.',
      principal: true,
    },
    {
      clave: 'deudas',
      etiqueta: 'Deudas',
      descripcion: 'Todas tus deudas, con búsqueda y filtros por estado, mes y servicio.',
      principal: true,
      pagina: () => import('@/pages/DeudasPage.vue'),
    },
    {
      clave: 'calendario',
      etiqueta: 'Calendario',
      descripcion: 'Los vencimientos del mes, por día, semana o en lista.',
      principal: true,
      pagina: () => import('@/pages/CalendarioPage.vue'),
    },
    {
      clave: 'ordenes',
      etiqueta: 'Órdenes',
      descripcion: 'Los pagos urgentes que enviaste a tu asistente y en qué quedaron.',
      principal: true,
    },
    {
      clave: 'servicios',
      etiqueta: 'Servicios',
      descripcion: 'Los servicios que pagas cada mes, con su empresa y código.',
      principal: true,
      pagina: () => import('@/pages/ServiciosPage.vue'),
    },
    {
      clave: 'asistentes',
      etiqueta: 'Asistentes',
      descripcion: 'La cuenta de tu asistente: crearla, activarla o restablecer su acceso.',
      principal: true,
      pagina: () => import('@/pages/AsistentesPage.vue'),
    },
    {
      clave: 'categorias',
      etiqueta: 'Categorías',
      descripcion: 'Agrupa tus servicios por tipo de gasto.',
      principal: false,
      pagina: () => import('@/pages/CategoriasPage.vue'),
    },
    {
      clave: 'limites',
      etiqueta: 'Límites',
      descripcion: 'Hasta cuánto puede pagar tu asistente sin pedirte aprobación.',
      principal: false,
      pagina: () => import('@/pages/LimitesPage.vue'),
    },
    {
      clave: 'historial',
      etiqueta: 'Historial',
      descripcion: 'Quién hizo qué y cuándo, en tu cuenta y en la de tu asistente.',
      principal: false,
      pagina: () => import('@/pages/HistorialPage.vue'),
    },
  ],
  asistente: [
    {
      clave: '',
      etiqueta: 'Bandeja',
      descripcion: 'Las deudas por atender, de la más urgente a la menos urgente.',
      principal: true,
    },
    {
      clave: 'calendario',
      etiqueta: 'Calendario',
      descripcion: 'Los vencimientos del mes, por día, semana o en lista.',
      principal: true,
      pagina: () => import('@/pages/CalendarioPage.vue'),
    },
    {
      clave: 'ruta',
      etiqueta: 'Ruta de pagos',
      descripcion: 'Los pagos presenciales agrupados por lugar, con el total que debes llevar.',
      principal: true,
    },
    {
      clave: 'comprobantes',
      etiqueta: 'Comprobantes',
      descripcion: 'Los comprobantes que subiste y el resultado de su validación.',
      principal: true,
    },
    {
      clave: 'servicios',
      etiqueta: 'Servicios',
      descripcion: 'Los servicios de tu gerente: regístralos y mantenlos al día.',
      principal: false,
      pagina: () => import('@/pages/ServiciosPage.vue'),
    },
  ],
}

export const CUENTA = 'cuenta'

export function nombreRuta(rol: Rol, clave: string): string {
  return clave ? `${rol}-${clave}` : `${rol}-inicio`
}
