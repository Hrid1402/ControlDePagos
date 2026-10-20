import { z } from 'zod'
import { esquemaContrasenaNueva, esquemaUsername } from '@/config/reglas'

export type EstadoCuenta = 'activa' | 'inactiva'

/** Fila de GET /asistentes (H03 CA01). */
export interface AsistenteFila {
  id: string
  nombres: string | null
  apellidos: string | null
  username: string
  estado: EstadoCuenta
  ultimo_ingreso: string | null
  creado_en: string
}

export interface EventoActivacion {
  accion: 'activada' | 'desactivada' | 'eliminada'
  realizada_por: string
  creado_en: string
}

/** GET /asistentes/:id con el historial de activaciones (CA17). */
export interface AsistenteDetalle extends AsistenteFila {
  historial: EventoActivacion[]
}

export interface Disponibilidad {
  disponible: boolean
  username: string
  sugerencia: string | null
}

/** Respuesta de crear o restablecer: la contraseña llega solo aquí, una vez (CA08 y CA16). */
export interface Credenciales {
  id: string
  nombre: string
  username: string
  contrasena: string
}

export interface ResultadoActivacion {
  activada: AsistenteFila
  desactivada: AsistenteFila | null
  ordenes_traspasadas: string[]
}

export interface ResultadoDesactivacion {
  asistente: AsistenteFila
  sesiones_cerradas: boolean
  sin_asistente_activa: boolean
  aviso: string | null
  ordenes_canceladas: string[]
}

export function nombreDe(cuenta: Pick<AsistenteFila, 'nombres' | 'apellidos' | 'username'>) {
  return [cuenta.nombres, cuenta.apellidos].filter(Boolean).join(' ') || cuenta.username
}

const PATRON_LETRAS = /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$/
const nombre = (vacio: string) =>
  z.string().trim().min(1, vacio).regex(PATRON_LETRAS, 'Usa solo letras, con tildes y ñ.')

/** Alta de asistente (CA04 a CA07): usuario y contraseña se generan o se eligen. */
export const esquemaCrearAsistente = z
  .object({
    nombres: nombre('Escribe sus nombres.'),
    apellidos: nombre('Escribe sus apellidos.'),
    modo_usuario: z.enum(['generar', 'elegir']),
    username: z.string(),
    modo_contrasena: z.enum(['generar', 'elegir']),
    contrasena: z.string(),
  })
  .superRefine((datos, contexto) => {
    const validar = (campo: 'username' | 'contrasena', esquema: z.ZodTypeAny) => {
      const resultado = esquema.safeParse(datos[campo])
      if (!resultado.success)
        contexto.addIssue({
          code: z.ZodIssueCode.custom,
          path: [campo],
          message: resultado.error.issues[0]?.message || 'Revisa este dato.',
        })
    }
    if (datos.modo_usuario === 'elegir') validar('username', esquemaUsername)
    if (datos.modo_contrasena === 'elegir') validar('contrasena', esquemaContrasenaNueva)
  })

/** Fecha y hora en Lima para mostrar; null si aún no ocurrió. */
export function fechaHora(iso: string | null, siVacio = 'Aún no ingresó'): string {
  if (!iso) return siVacio
  return new Date(iso).toLocaleString('es-PE', {
    timeZone: 'America/Lima',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function iniciales(cuenta: Pick<AsistenteFila, 'nombres' | 'apellidos' | 'username'>) {
  const letras = [cuenta.nombres, cuenta.apellidos].map((p) => p?.trim()[0]).filter(Boolean)
  return (letras.length ? letras.join('') : cuenta.username[0] || '').toLocaleUpperCase('es')
}
