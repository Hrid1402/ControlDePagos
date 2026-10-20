// Historial de acciones (H34, TASK-19): forma de los registros y cómo se leen en pantalla.
// Los códigos de acción vienen del servidor (app/services/auditoria.py); aquí se traducen a
// frases para que el gerente lea «Rosa Melgar inició un pago» y no «pago_iniciado».

export interface RegistroHistorial {
  id: string
  usuario_id: string | null
  usuario_nombre: string
  accion: string
  entidad: string
  entidad_id: string | null
  detalle: Record<string, unknown>
  dispositivo: string | null
  ip: string | null
  creado_en: string
}

export interface PaginaHistorial {
  items: RegistroHistorial[]
  total: number
  page: number
}

export interface FiltrosHistorial {
  usuario: string
  accion: string
  desde: string
  hasta: string
}

export type Grupo =
  'acceso' | 'cuenta' | 'asistentes' | 'deudas' | 'pagos' | 'ordenes' | 'configuracion'

export const GRUPOS: Record<Grupo, string> = {
  acceso: 'Acceso',
  cuenta: 'Mi cuenta',
  asistentes: 'Asistentes',
  deudas: 'Deudas',
  pagos: 'Pagos y aprobaciones',
  ordenes: 'Órdenes urgentes',
  configuracion: 'Categorías y servicios',
}

interface Accion {
  grupo: Grupo
  /** Lo que hizo, después del nombre de quien lo hizo. */
  frase: string
  /** Nombre corto para el filtro. */
  etiqueta: string
  alerta?: boolean
}

export const ACCIONES: Record<string, Accion> = {
  login_exitoso: { grupo: 'acceso', frase: 'inició sesión', etiqueta: 'Ingreso' },
  login_fallido: {
    grupo: 'acceso',
    frase: 'intentó ingresar sin éxito',
    etiqueta: 'Ingreso fallido',
    alerta: true,
  },
  contrasena_restablecida: {
    grupo: 'acceso',
    frase: 'restableció una contraseña',
    etiqueta: 'Contraseña restablecida',
  },
  perfil_actualizado: {
    grupo: 'cuenta',
    frase: 'actualizó sus datos personales',
    etiqueta: 'Datos personales',
  },
  usuario_cambiado: {
    grupo: 'cuenta',
    frase: 'cambió su nombre de usuario',
    etiqueta: 'Cambio de usuario',
  },
  contrasena_cambiada: {
    grupo: 'cuenta',
    frase: 'cambió su contraseña',
    etiqueta: 'Cambio de contraseña',
  },
  politica_aceptada: {
    grupo: 'cuenta',
    frase: 'aceptó la política de privacidad',
    etiqueta: 'Política de privacidad',
  },
  cuenta_creada: { grupo: 'asistentes', frase: 'creó una cuenta', etiqueta: 'Cuenta creada' },
  cuenta_activada: {
    grupo: 'asistentes',
    frase: 'activó una cuenta de asistente',
    etiqueta: 'Cuenta activada',
  },
  cuenta_desactivada: {
    grupo: 'asistentes',
    frase: 'desactivó una cuenta de asistente',
    etiqueta: 'Cuenta desactivada',
  },
  cuenta_eliminada: {
    grupo: 'asistentes',
    frase: 'eliminó una cuenta de asistente',
    etiqueta: 'Cuenta eliminada',
    alerta: true,
  },
  deuda_creada: { grupo: 'deudas', frase: 'registró una deuda', etiqueta: 'Deuda registrada' },
  deuda_monto_cambiado: {
    grupo: 'deudas',
    frase: 'cambió el monto de una deuda',
    etiqueta: 'Cambio de monto',
  },
  deuda_estado_cambiado: {
    grupo: 'deudas',
    frase: 'cambió el estado de una deuda',
    etiqueta: 'Cambio de estado',
  },
  deuda_fijada: {
    grupo: 'deudas',
    frase: 'fijó una deuda en su bandeja',
    etiqueta: 'Deuda fijada',
  },
  deuda_pospuesta: {
    grupo: 'deudas',
    frase: 'pospuso una deuda para mañana',
    etiqueta: 'Deuda pospuesta',
  },
  pago_iniciado: { grupo: 'pagos', frase: 'inició un pago', etiqueta: 'Pago iniciado' },
  pago_inicio_cancelado: {
    grupo: 'pagos',
    frase: 'canceló un pago en curso',
    etiqueta: 'Pago cancelado',
  },
  aprobacion_solicitada: {
    grupo: 'pagos',
    frase: 'pidió aprobar un pago',
    etiqueta: 'Aprobación pedida',
  },
  aprobacion_aprobada: { grupo: 'pagos', frase: 'aprobó un pago', etiqueta: 'Pago aprobado' },
  aprobacion_rechazada: { grupo: 'pagos', frase: 'rechazó un pago', etiqueta: 'Pago rechazado' },
  orden_vista: { grupo: 'ordenes', frase: 'vio una orden urgente', etiqueta: 'Orden vista' },
  orden_aceptada: {
    grupo: 'ordenes',
    frase: 'aceptó una orden urgente',
    etiqueta: 'Orden aceptada',
  },
  orden_rechazada: {
    grupo: 'ordenes',
    frase: 'rechazó una orden urgente',
    etiqueta: 'Orden rechazada',
  },
  orden_traspasada: {
    grupo: 'ordenes',
    frase: 'traspasó una orden urgente',
    etiqueta: 'Orden traspasada',
  },
  orden_cancelada: {
    grupo: 'ordenes',
    frase: 'canceló una orden urgente',
    etiqueta: 'Orden cancelada',
  },
  categoria_creada: {
    grupo: 'configuracion',
    frase: 'creó una categoría',
    etiqueta: 'Categoría creada',
  },
  categoria_actualizada: {
    grupo: 'configuracion',
    frase: 'editó una categoría',
    etiqueta: 'Categoría editada',
  },
  categoria_eliminada: {
    grupo: 'configuracion',
    frase: 'eliminó una categoría',
    etiqueta: 'Categoría eliminada',
  },
  servicio_creado: {
    grupo: 'configuracion',
    frase: 'registró un servicio',
    etiqueta: 'Servicio registrado',
  },
  servicio_actualizado: {
    grupo: 'configuracion',
    frase: 'editó un servicio',
    etiqueta: 'Servicio editado',
  },
  servicio_dado_de_baja: {
    grupo: 'configuracion',
    frase: 'dio de baja un servicio',
    etiqueta: 'Servicio dado de baja',
  },
  servicio_reactivado: {
    grupo: 'configuracion',
    frase: 'reactivó un servicio',
    etiqueta: 'Servicio reactivado',
  },
}

/** Una acción nueva del servidor sin traducir todavía se lee igual, sin guiones bajos. */
export function accionDe(codigo: string): Accion {
  return (
    ACCIONES[codigo] ?? {
      grupo: 'configuracion',
      frase: codigo.replace(/_/g, ' '),
      etiqueta: codigo.replace(/_/g, ' '),
    }
  )
}

/** Opciones del filtro de acción, agrupadas como en la lista. */
export const OPCIONES_ACCION = (Object.keys(GRUPOS) as Grupo[]).map((grupo) => ({
  grupo: GRUPOS[grupo],
  acciones: Object.entries(ACCIONES)
    .filter(([, accion]) => accion.grupo === grupo)
    .map(([valor, accion]) => ({ valor, etiqueta: accion.etiqueta })),
}))

const ZONA = 'America/Lima'
const diaLima = (fecha: Date) => fecha.toLocaleDateString('en-CA', { timeZone: ZONA })

/** Día de Lima de un registro, para agruparlos. */
export function dia(iso: string): string {
  return diaLima(new Date(iso))
}

export function tituloDia(diaIso: string, ahora = new Date()): string {
  const ayer = new Date(ahora.getTime() - 24 * 60 * 60 * 1000)
  if (diaIso === diaLima(ahora)) return 'Hoy'
  if (diaIso === diaLima(ayer)) return 'Ayer'
  const fecha = new Date(`${diaIso}T12:00:00-05:00`)
  const mismoAnio = diaIso.slice(0, 4) === diaLima(ahora).slice(0, 4)
  const texto = fecha.toLocaleDateString('es-PE', {
    timeZone: ZONA,
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    ...(mismoAnio ? {} : { year: 'numeric' }),
  })
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

export function hora(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-PE', {
    timeZone: ZONA,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function iniciales(nombre: string): string {
  const partes = nombre.trim().split(/\s+/).filter(Boolean)
  if (!partes.length) return '?'
  const [primero, segundo] = partes
  return ((primero?.[0] ?? '') + (segundo?.[0] ?? '')).toUpperCase()
}

/** «Chrome en Android» a partir del User-Agent; lo demás se muestra tal cual, recortado. */
export function dispositivo(agente: string | null): string | null {
  if (!agente) return null
  const navegador = /Edg\//.test(agente)
    ? 'Edge'
    : /OPR\//.test(agente)
      ? 'Opera'
      : /Firefox\//.test(agente)
        ? 'Firefox'
        : /Chrome\//.test(agente)
          ? 'Chrome'
          : /Safari\//.test(agente)
            ? 'Safari'
            : null
  const sistema = /Android/.test(agente)
    ? 'Android'
    : /iPhone|iPad/.test(agente)
      ? 'iPhone o iPad'
      : /Windows/.test(agente)
        ? 'Windows'
        : /Mac OS X/.test(agente)
          ? 'Mac'
          : /Linux/.test(agente)
            ? 'Linux'
            : null
  if (navegador && sistema) return `${navegador} en ${sistema}`
  if (navegador || sistema) return navegador ?? sistema
  return agente.length > 60 ? `${agente.slice(0, 57)}…` : agente
}

const CAMPOS: Record<string, string> = {
  monto: 'Monto',
  moneda: 'Moneda',
  saldo: 'Saldo',
  motivo: 'Motivo',
  estado: 'Estado',
  estado_anterior: 'Estado anterior',
  estado_nuevo: 'Estado nuevo',
  periodo: 'Periodo',
  fecha_vencimiento: 'Vence',
  numero_recibo: 'N.º de recibo',
  vencida: 'Ya vencida',
  version: 'Versión',
  nombre: 'Nombre',
  nombres: 'Nombres',
  apellidos: 'Apellidos',
  celular: 'Celular',
  correo: 'Correo',
  tipo_documento: 'Tipo de documento',
  numero_documento: 'Documento',
  username: 'Usuario',
  anterior: 'Antes',
  nuevo: 'Ahora',
  oculta_hasta: 'Oculta hasta',
  autorizacion: 'Autorizado por',
  tipo: 'Tipo',
  empresa_nombre: 'Empresa',
  codigo_suministro: 'Código',
  alias: 'Nombre del servicio',
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const FECHA_HORA = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

function valorLegible(valor: unknown): string | null {
  if (valor === null || valor === undefined || valor === '') return null
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  if (Array.isArray(valor)) return valor.length ? `${valor.length} elementos` : null
  if (typeof valor === 'object') return null
  const texto = String(valor)
  if (UUID.test(texto)) return null
  if (FECHA_HORA.test(texto)) return `${tituloDia(dia(texto))}, ${hora(texto)}`
  return texto.replace(/_/g, ' ')
}

export interface Dato {
  campo: string
  valor: string
}

/** Detalle del registro en pares campo y valor; omite identificadores internos. */
export function datosDe(detalle: Record<string, unknown>): Dato[] {
  const datos: Dato[] = []
  for (const [clave, valor] of Object.entries(detalle)) {
    if (clave === 'id' || clave.endsWith('_id') || clave.endsWith('_por')) continue
    const campo = CAMPOS[clave] ?? clave.charAt(0).toUpperCase() + clave.slice(1).replace(/_/g, ' ')
    if (valor && typeof valor === 'object' && !Array.isArray(valor) && 'nuevo' in valor) {
      const cambio = valor as { anterior?: unknown; nuevo?: unknown }
      const antes = valorLegible(cambio.anterior) ?? 'vacío'
      const ahora = valorLegible(cambio.nuevo) ?? 'vacío'
      datos.push({ campo, valor: `de ${antes} a ${ahora}` })
      continue
    }
    const legible = valorLegible(valor)
    if (legible !== null) datos.push({ campo, valor: legible })
  }
  return datos
}

// Acciones sobre la cuenta de otra persona: la frase nombra a quién afectaron.
const SOBRE_CUENTA: Record<string, string> = {
  cuenta_creada: 'creó la cuenta de',
  cuenta_activada: 'activó la cuenta de',
  cuenta_desactivada: 'desactivó la cuenta de',
  cuenta_eliminada: 'eliminó la cuenta de',
  contrasena_restablecida: 'restableció la contraseña de',
}

const textoNoVacio = (valor: unknown): valor is string =>
  typeof valor === 'string' && valor.trim() !== ''

/**
 * Lo que hizo, nombrando la cuenta afectada si se conoce: por la lista de personas del gerente,
 * o por el nombre que guardó el registro (una cuenta eliminada ya no está en la lista).
 */
export function fraseDe(registro: RegistroHistorial, nombres: Record<string, string>): string {
  const prefijo = SOBRE_CUENTA[registro.accion]
  const propia = registro.entidad_id !== null && registro.entidad_id === registro.usuario_id
  if (registro.accion === 'contrasena_restablecida' && propia) return 'restableció su contraseña'
  if (!prefijo || registro.entidad !== 'usuario' || propia) return accionDe(registro.accion).frase
  const { nombre, nombres: dados, apellidos } = registro.detalle
  const afectada =
    (registro.entidad_id && nombres[registro.entidad_id]) ||
    (textoNoVacio(nombre) && nombre) ||
    (textoNoVacio(dados) && textoNoVacio(apellidos) && `${dados} ${apellidos}`) ||
    ''
  return afectada ? `${prefijo} ${afectada}` : accionDe(registro.accion).frase
}
