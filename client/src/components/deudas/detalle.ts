// Contrato de pantalla del detalle de deuda (H17, TASK-52). Refleja GET /api/v1/deudas/:id de
// TASK-53 y los comentarios de TASK-54; la pantalla con datos reales es TASK-55.
import type { CategoriaDeuda } from './listado'
import type { EstadoDeuda } from './estados'
import type { Moneda } from './modelo'

export type AccionDeuda =
  | 'iniciar_pago'
  | 'cancelar_inicio'
  | 'adjuntar_comprobante'
  | 'comentar'
  | 'editar'
  | 'anular'
  | 'ordenar_urgente'

export interface ComprobanteDeLaDeuda {
  id: string
  estado: 'procesando' | 'validado' | 'por_confirmar' | 'en_revision' | 'rechazado'
  motivo_codigo: string | null
  observacion: string | null
  monto: string | null
  monto_aplicado: string
  moneda: Moneda
  subido_por: string
  creado_en: string
  reemplaza_a_id: string | null
}

export interface EventoDeuda {
  tipo: string
  fecha: string
  actor: { nombre: string; rol: string | null } | null
  detalle: Record<string, unknown>
}

export interface CambioMonto {
  monto_anterior: string
  monto_nuevo: string
  origen: string
  usuario: string | null
  creado_en: string
}

export interface DetalleDeuda {
  id: string
  servicio: {
    id: string
    empresa: string
    alias: string | null
    codigo_suministro: string
    titular: string | null
    lugar_pago: string | null
    notas: string | null
  }
  categoria: CategoriaDeuda
  periodo: string
  estado: EstadoDeuda
  origen: string
  moneda: Moneda
  monto: string | null
  pagado: string
  saldo: string | null
  monto_proyectado: string | null
  vencida: boolean
  fecha_emision: string | null
  fecha_vencimiento: string
  fecha_estimada: string | null
  fecha_corte: string | null
  pago_minimo: string | null
  pago_total: string | null
  numero_recibo: string | null
  recibo_enlace: string | null
  cuota_numero: number | null
  cuotas_total: number | null
  en_proceso: { usuario_id: string; rol: string; nombre: string; desde: string | null } | null
  orden_urgente: { id: string; estado: string; plazo: string | null } | null
  creado_en: string
  comprobantes: ComprobanteDeLaDeuda[]
  historial_montos: CambioMonto[]
  linea_tiempo: EventoDeuda[]
  acciones: AccionDeuda[]
}

export interface ComentarioDeuda {
  id: string
  texto: string
  autor: string
  rol: string
  propio: boolean
  creado_en: string
}

export const LARGO_COMENTARIO = 500

export const RESULTADOS_COMPROBANTE: Record<
  ComprobanteDeLaDeuda['estado'],
  { etiqueta: string; tono: 'exito' | 'info' | 'peligro' | 'proceso'; icono: string }
> = {
  procesando: { etiqueta: 'Validando', tono: 'proceso', icono: 'pi-spinner' },
  por_confirmar: { etiqueta: 'Por confirmar', tono: 'info', icono: 'pi-hourglass' },
  en_revision: { etiqueta: 'En revisión', tono: 'info', icono: 'pi-eye' },
  validado: { etiqueta: 'Validado', tono: 'exito', icono: 'pi-check-circle' },
  rechazado: { etiqueta: 'Rechazado', tono: 'peligro', icono: 'pi-times-circle' },
}

const EVENTOS: Record<string, string> = {
  deuda_creada: 'Registró la deuda',
  deuda_monto_cambiado: 'Cambió el monto',
  deuda_estado_cambiado: 'Cambió el estado',
  deuda_fijada: 'Fijó la deuda como prioritaria',
  deuda_pospuesta: 'La pospuso hasta mañana',
  pago_iniciado: 'Empezó a pagarla',
  pago_inicio_cancelado: 'Canceló el pago en curso',
  aprobacion_solicitada: 'Pidió aprobación para pagarla',
  aprobacion_aprobada: 'Aprobó el pago',
  aprobacion_rechazada: 'Rechazó el pago',
  orden_vista: 'Vio la orden urgente',
  orden_aceptada: 'Aceptó la orden urgente',
  orden_rechazada: 'Rechazó la orden urgente',
  orden_cancelada: 'Canceló la orden urgente',
  orden_traspasada: 'La orden pasó a la nueva asistente',
  comprobante_subido: 'Adjuntó un comprobante',
  comprobante_reemplazado: 'Reemplazó un comprobante rechazado',
  comprobante_aprobado: 'Aprobó el comprobante',
  comprobante_rechazado: 'Rechazó el comprobante',
  comprobante_validado: 'El comprobante se validó solo',
  comprobante_en_revision: 'El comprobante quedó en revisión',
}

/** Texto de un evento de la línea de tiempo. Un tipo nuevo se lee sin guiones bajos. */
export function textoEvento(evento: EventoDeuda): string {
  if (evento.tipo === 'comprobante_rechazado' && !evento.actor) return 'El comprobante se rechazó'
  if (evento.tipo === 'deuda_creada' && !evento.actor) return 'Se creó sola cada mes'
  const texto = EVENTOS[evento.tipo] ?? evento.tipo.split('_').join(' ')
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

/** «20 oct., 10:35». */
export function fechaHora(valor: string): string {
  return new Date(valor).toLocaleString('es-PE', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Lima',
  })
}
