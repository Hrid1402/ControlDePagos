// Copia de server/app/core/reglas.py: si cambia una regla allí, cambia aquí y en sus pruebas.
import { z } from 'zod'

export const LARGO_MINIMO_USERNAME = 3
export const LARGO_MAXIMO_USERNAME = 30
export const PATRON_USERNAME = /^[a-zA-Z0-9._-]+$/
export const LARGO_MINIMO_CONTRASENA = 8
export const BYTES_MAXIMOS_CONTRASENA = 72

export const MENSAJE_CONTRASENA_LARGA = 'La contraseña es demasiado larga.'
export const MENSAJE_CONTRASENA_CORTA = `La contraseña debe tener al menos ${LARGO_MINIMO_CONTRASENA} caracteres.`
export const MENSAJE_CONTRASENA_DEBIL =
  'La contraseña debe tener mayúscula, minúscula, número y símbolo.'

export const requisitosContrasena = [
  { etiqueta: '8 caracteres', cumple: (s: string) => [...s].length >= LARGO_MINIMO_CONTRASENA },
  { etiqueta: 'Mayúscula', cumple: (s: string) => /\p{Lu}/u.test(s) },
  { etiqueta: 'Minúscula', cumple: (s: string) => /\p{Ll}/u.test(s) },
  { etiqueta: 'Número', cumple: (s: string) => /\p{Nd}/u.test(s) },
  { etiqueta: 'Símbolo', cumple: (s: string) => /[^\p{L}\p{N}\s]/u.test(s) },
]

export function bytesDe(texto: string): number {
  return new TextEncoder().encode(texto).length
}

/** Motivo por el que la contraseña no cumple, o null si cumple. Sin recortar espacios. */
export function motivoContrasena(contrasena: string): string | null {
  if (bytesDe(contrasena) > BYTES_MAXIMOS_CONTRASENA) return MENSAJE_CONTRASENA_LARGA
  if ([...contrasena].length < LARGO_MINIMO_CONTRASENA) return MENSAJE_CONTRASENA_CORTA
  if (!requisitosContrasena.every((requisito) => requisito.cumple(contrasena)))
    return MENSAJE_CONTRASENA_DEBIL
  return null
}

export const esquemaContrasenaNueva = z.string().superRefine((valor, contexto) => {
  const motivo = motivoContrasena(valor)
  if (motivo) contexto.addIssue({ code: z.ZodIssueCode.custom, message: motivo })
})

export const esquemaUsername = z
  .string()
  .trim()
  .min(1, 'Escribe tu usuario.')
  .min(
    LARGO_MINIMO_USERNAME,
    `El usuario debe tener de ${LARGO_MINIMO_USERNAME} a ${LARGO_MAXIMO_USERNAME} caracteres.`,
  )
  .max(
    LARGO_MAXIMO_USERNAME,
    `El usuario debe tener de ${LARGO_MINIMO_USERNAME} a ${LARGO_MAXIMO_USERNAME} caracteres.`,
  )
  .regex(
    PATRON_USERNAME,
    'El usuario solo puede tener letras sin tilde, números, punto, guion y guion bajo.',
  )
