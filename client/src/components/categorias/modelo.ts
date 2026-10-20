// Categorías de deuda (H09, TASK-29): forma, opciones del formulario y reglas que la pantalla
// explica antes de que la API las rechace.
import { z } from 'zod'

export type TipoCategoria = 'servicio_variable' | 'monto_fijo' | 'tarjeta' | 'prestamo'

export interface Categoria {
  id: string
  nombre: string
  color: string
  icono: string
  tipo: TipoCategoria
  precargada: boolean
  cantidad_servicios: number
  cantidad_deudas: number
}

/** CA03: el tipo decide qué pide cada deuda; la pantalla lo dice al elegirlo. */
export const TIPOS: { valor: TipoCategoria; etiqueta: string; pide: string }[] = [
  {
    valor: 'servicio_variable',
    etiqueta: 'Servicio variable',
    pide: 'El monto cambia cada mes y llega con el recibo, como la luz o el agua.',
  },
  {
    valor: 'monto_fijo',
    etiqueta: 'Monto fijo',
    pide: 'Se paga lo mismo cada mes, como internet o una suscripción.',
  },
  {
    valor: 'tarjeta',
    etiqueta: 'Tarjeta',
    pide: 'Pide el pago mínimo y el total del estado de cuenta.',
  },
  {
    valor: 'prestamo',
    etiqueta: 'Préstamo en cuotas',
    pide: 'Pide el total, el número de cuotas y arma el cronograma.',
  },
]

export const etiquetaTipo = (tipo: string) => TIPOS.find((t) => t.valor === tipo)?.etiqueta ?? tipo

/** Los colores de las precargadas y algunos más, todos legibles con su ícono encima. */
export const COLORES: { valor: string; etiqueta: string }[] = [
  { valor: '#F59E0B', etiqueta: 'Ámbar' },
  { valor: '#0EA5E9', etiqueta: 'Celeste' },
  { valor: '#F97316', etiqueta: 'Naranja' },
  { valor: '#8B5CF6', etiqueta: 'Violeta' },
  { valor: '#EF4444', etiqueta: 'Rojo' },
  { valor: '#10B981', etiqueta: 'Verde' },
  { valor: '#64748B', etiqueta: 'Gris' },
  { valor: '#075A50', etiqueta: 'Verde petróleo' },
  { valor: '#DB2777', etiqueta: 'Fucsia' },
  { valor: '#2563EB', etiqueta: 'Azul' },
  { valor: '#84CC16', etiqueta: 'Lima' },
  { valor: '#92400E', etiqueta: 'Café' },
]

export const ICONOS: { valor: string; etiqueta: string }[] = [
  { valor: 'pi-tag', etiqueta: 'Etiqueta' },
  { valor: 'pi-bolt', etiqueta: 'Luz' },
  { valor: 'pi-eye-dropper', etiqueta: 'Agua' },
  { valor: 'pi-gauge', etiqueta: 'Gas' },
  { valor: 'pi-wifi', etiqueta: 'Internet' },
  { valor: 'pi-mobile', etiqueta: 'Celular' },
  { valor: 'pi-credit-card', etiqueta: 'Tarjeta' },
  { valor: 'pi-building-columns', etiqueta: 'Banco' },
  { valor: 'pi-home', etiqueta: 'Casa' },
  { valor: 'pi-building', etiqueta: 'Edificio' },
  { valor: 'pi-car', etiqueta: 'Auto' },
  { valor: 'pi-graduation-cap', etiqueta: 'Estudios' },
  { valor: 'pi-heart', etiqueta: 'Salud' },
  { valor: 'pi-shield', etiqueta: 'Seguro' },
  { valor: 'pi-shopping-cart', etiqueta: 'Compras' },
  { valor: 'pi-wallet', etiqueta: 'Billetera' },
]

/** Tinta del ícono sobre el color de la categoría: oscura en colores claros, clara en oscuros. */
export function tintaSobre(color: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const canal = parseInt(color.slice(i, i + 2), 16) / 255
    return canal <= 0.03928 ? canal / 12.92 : ((canal + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  const luminancia = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return luminancia > 0.3 ? '#192c29' : '#ffffff'
}

export const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`

/** CA02: nombre de 1 a 40 caracteres; la unicidad sin mayúsculas la confirma la API. */
export const esquemaCategoria = z.object({
  nombre: z.string().trim().min(1, 'Escribe un nombre.').max(40, 'Usa como máximo 40 caracteres.'),
  tipo: z.enum(['servicio_variable', 'monto_fijo', 'tarjeta', 'prestamo'], {
    message: 'Elige un tipo.',
  }),
  color: z.string().regex(/^#[0-9A-Fa-f]{6}$/, 'Elige un color.'),
  icono: z.string().min(1, 'Elige un ícono.'),
})

/** Destinos válidos para los servicios de una categoría: con deudas, solo del mismo tipo. */
export function destinosPara(origen: Categoria, todas: Categoria[]): Categoria[] {
  return todas.filter(
    (c) => c.id !== origen.id && (origen.cantidad_deudas === 0 || c.tipo === origen.tipo),
  )
}
