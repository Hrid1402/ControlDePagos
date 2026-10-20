import 'vue-router'
import type { Rol } from './api'
declare module 'vue-router' {
  interface RouteMeta {
    publica?: boolean
    libre?: boolean
    rol?: Rol
    titulo?: string
  }
}
