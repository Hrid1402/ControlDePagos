// Contrato de pantalla de H10 (TASK-31). Los datos llegan en TASK-34 desde GET /servicios,
// GET /servicios/:id, GET /empresas y GET /categorias; aquí se definen su forma, su lectura y
// las reglas del formulario.
import { z } from 'zod'

export type LugarPago =
  'agente_bcp' | 'agente_kasnet' | 'ventanilla_empresa' | 'banca_movil' | 'otro'
export type EstadoServicio = 'activo' | 'baja'
export type FiltroEstado = EstadoServicio | 'todos'

export interface CategoriaServicio {
  id: string
  nombre: string
  tipo: string
  color: string
  icono: string
}

export interface Empresa {
  id: string
  nombre: string
  tipo_servicio: 'luz' | 'agua' | 'gas' | 'telecomunicaciones' | 'otro'
  patron_codigo: string | null
}

export interface Servicio {
  id: string
  categoria: CategoriaServicio
  empresa_id: string | null
  empresa: string
  empresa_manual: boolean
  codigo_suministro: string
  titular: string | null
  alias: string | null
  lugar_pago: LugarPago | null
  notas: string | null
  estado: EstadoServicio
}

/** El detalle trae las deudas sin pagar: el formulario advierte antes de cambiar el código. */
export interface ServicioDetalle extends Servicio {
  deudas_pendientes: number
}

/** Lo que envía el formulario: empresa del catálogo por id, o escrita a mano (CA01). */
export interface DatosServicio {
  categoria_id: string
  empresa_id: string | null
  empresa_nombre: string | null
  codigo_suministro: string
  titular: string | null
  alias: string | null
  lugar_pago: LugarPago
  notas: string | null
}

/** CA05. Banca móvil o Yape no entra en la ruta de pagos presenciales. */
export const LUGARES_PAGO: {
  valor: LugarPago
  etiqueta: string
  /** Cómo se lee en la lista: «Se paga en un agente BCP». */
  en: string
  icono: string
  nota?: string
}[] = [
  {
    valor: 'agente_bcp',
    etiqueta: 'Agente BCP',
    en: 'un agente BCP',
    icono: 'pi-building-columns',
  },
  { valor: 'agente_kasnet', etiqueta: 'Agente KasNet', en: 'un agente KasNet', icono: 'pi-shop' },
  {
    valor: 'ventanilla_empresa',
    etiqueta: 'Ventanilla de la empresa',
    en: 'la ventanilla de la empresa',
    icono: 'pi-building',
  },
  {
    valor: 'banca_movil',
    etiqueta: 'Banca móvil o Yape',
    en: 'banca móvil o Yape',
    icono: 'pi-mobile',
    nota: 'No entra en la ruta de pagos presenciales.',
  },
  { valor: 'otro', etiqueta: 'Otro lugar', en: 'otro lugar', icono: 'pi-map-marker' },
]

export const lugarEn = (lugar: string | null) =>
  LUGARES_PAGO.find((l) => l.valor === lugar)?.en ?? null

export const GRUPOS_EMPRESA: Record<Empresa['tipo_servicio'], string> = {
  luz: 'Luz',
  agua: 'Agua',
  gas: 'Gas',
  telecomunicaciones: 'Telefonía e internet',
  otro: 'Otras',
}

/** Valor del selector de empresa cuando no está en el catálogo. */
export const OTRA_EMPRESA = 'otra'

/** Nombre con el que se reconoce el servicio: su alias, o la empresa si no tiene. */
export const nombreServicio = (s: Servicio) => s.alias || s.empresa

const opcional = (maximo: number, mensaje: string) => z.string().trim().max(maximo, mensaje)

/**
 * CA01 a CA06. El código se valida con el patrón de la empresa elegida cuando lo tiene (CA02);
 * el duplicado de empresa y código lo confirma la API (CA03).
 */
export function esquemaServicio(empresas: Empresa[]) {
  return z
    .object({
      categoria_id: z.string().min(1, 'Elige una categoría.'),
      empresa: z.string().min(1, 'Elige la empresa o «Otra empresa».'),
      empresa_nombre: opcional(80, 'Usa como máximo 80 caracteres.'),
      codigo_suministro: z
        .string()
        .trim()
        .min(1, 'Escribe el código de suministro.')
        .max(40, 'Usa como máximo 40 caracteres.'),
      titular: opcional(120, 'Usa como máximo 120 caracteres.'),
      alias: opcional(60, 'Usa como máximo 60 caracteres.'),
      lugar_pago: z.string().min(1, 'Elige dónde se paga.'),
      notas: opcional(500, 'Usa como máximo 500 caracteres.'),
    })
    .superRefine((datos, contexto) => {
      if (datos.empresa === OTRA_EMPRESA && !datos.empresa_nombre) {
        contexto.addIssue({
          code: 'custom',
          path: ['empresa_nombre'],
          message: 'Escribe el nombre de la empresa.',
        })
      }
      const empresa = empresas.find((e) => e.id === datos.empresa)
      const codigo = datos.codigo_suministro.replace(/\s+/g, '')
      if (
        empresa?.patron_codigo &&
        codigo &&
        !new RegExp(`^(?:${empresa.patron_codigo})$`).test(codigo)
      ) {
        contexto.addIssue({
          code: 'custom',
          path: ['codigo_suministro'],
          message: `Revisa el código: no tiene el formato de ${empresa.nombre}.`,
        })
      }
    })
}

export function aDatos(valores: Record<string, unknown>): DatosServicio {
  const texto = (campo: string) => String(valores[campo] ?? '').trim() || null
  const otra = valores.empresa === OTRA_EMPRESA
  return {
    categoria_id: String(valores.categoria_id),
    empresa_id: otra ? null : String(valores.empresa),
    empresa_nombre: otra ? texto('empresa_nombre') : null,
    codigo_suministro: String(valores.codigo_suministro).trim(),
    titular: texto('titular'),
    alias: texto('alias'),
    lugar_pago: valores.lugar_pago as LugarPago,
    notas: texto('notas'),
  }
}

export function valoresDe(servicio: ServicioDetalle | null) {
  return {
    categoria_id: servicio?.categoria.id ?? '',
    empresa: servicio ? (servicio.empresa_id ?? OTRA_EMPRESA) : '',
    empresa_nombre: servicio?.empresa_manual ? servicio.empresa : '',
    codigo_suministro: servicio?.codigo_suministro ?? '',
    titular: servicio?.titular ?? '',
    alias: servicio?.alias ?? '',
    lugar_pago: servicio?.lugar_pago ?? '',
    notas: servicio?.notas ?? '',
  }
}
