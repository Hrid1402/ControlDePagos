// Reglas copiadas de server/app/schemas/usuarios.py: si cambian allí, cambian aquí y en sus pruebas.
import { z } from 'zod'
import { esquemaContrasenaNueva, esquemaUsername } from '@/config/reglas'
import type { Rol } from './api'

export type TipoDocumento = 'dni' | 'ce' | 'pasaporte'

export const TIPOS_DOCUMENTO: { valor: TipoDocumento; etiqueta: string }[] = [
  { valor: 'dni', etiqueta: 'DNI' },
  { valor: 'ce', etiqueta: 'Carné de extranjería' },
  { valor: 'pasaporte', etiqueta: 'Pasaporte' },
]

/** Respuesta de GET /usuarios/perfil. Los datos aún no registrados llegan como null. */
export interface PerfilCuenta {
  id: string
  username: string
  rol: Rol
  nombres: string | null
  apellidos: string | null
  tipo_documento: TipoDocumento | null
  numero_documento: string | null
  correo: string | null
  celular: string | null
  politica_version: string | null
  politica_aceptada_en: string | null
  /** Aún no los envía la API (brechas de TASK-7 y TASK-9); la pantalla los usa en cuanto lleguen. */
  cambios_restantes?: number
  contrasena_inicial?: boolean
}

/** Señales que la API todavía no expone (brechas de TASK-7 y TASK-9). null mientras falten:
 *  la pantalla no las calcula ni las inventa. */
export interface SenalesCuenta {
  cambiosRestantes: number | null
  contrasenaInicial: boolean | null
}

const PATRON_LETRAS = /^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$/
const PATRON_CELULAR = /^9\d{8}$/

const nombre = (vacio: string) =>
  z.string().trim().min(1, vacio).regex(PATRON_LETRAS, 'Usa solo letras, con tildes y ñ.')

export const esquemaDatosPersonales = z
  .object({
    nombres: nombre('Escribe tus nombres.'),
    apellidos: nombre('Escribe tus apellidos.'),
    tipo_documento: z.enum(['', 'dni', 'ce', 'pasaporte']),
    numero_documento: z.string().trim(),
    correo: z.string().trim().min(1, 'Escribe tu correo.').email('Revisa el formato del correo.'),
    celular: z.string().trim().regex(PATRON_CELULAR, 'El celular tiene 9 dígitos y empieza con 9.'),
  })
  .superRefine((datos, contexto) => {
    const { tipo_documento: tipo, numero_documento: numero } = datos
    const error = (campo: 'tipo_documento' | 'numero_documento', message: string) =>
      contexto.addIssue({ code: z.ZodIssueCode.custom, path: [campo], message })
    if (!tipo && numero) error('tipo_documento', 'Elige el tipo de documento.')
    else if (tipo && !numero) error('numero_documento', 'Escribe el número de documento.')
    else if (tipo === 'dni' && !/^\d{8}$/.test(numero))
      error('numero_documento', 'El DNI tiene 8 dígitos.')
    else if (tipo && tipo !== 'dni' && !/^[A-Za-z0-9]{9,12}$/.test(numero))
      error('numero_documento', 'Debe tener de 9 a 12 letras o números, sin espacios.')
  })

export function esquemaCambioUsuario(actual: string) {
  return z.object({
    username: esquemaUsername.refine((nuevo) => nuevo.toLowerCase() !== actual.toLowerCase(), {
      message: 'El nuevo usuario es igual al actual.',
    }),
  })
}

export const esquemaCambioContrasena = z
  .object({
    contrasena_actual: z.string().min(1, 'Escribe tu contraseña actual.'),
    contrasena_nueva: esquemaContrasenaNueva,
    confirmacion: z.string().min(1, 'Confirma la nueva contraseña.'),
  })
  .refine((v) => v.contrasena_nueva === v.confirmacion, {
    message: 'Las contraseñas no coinciden.',
    path: ['confirmacion'],
  })
