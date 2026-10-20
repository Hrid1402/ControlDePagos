import type { VistaCalendario } from './modelo'

export const DIAS_SEMANA = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
const idioma = 'es-PE'

export function fechaLocal(fecha: string): Date {
  const [anio = 0, mes = 1, dia = 1] = fecha.split('-').map(Number)
  return new Date(anio, mes - 1, dia)
}

export function claveFecha(fecha: Date): string {
  const anio = fecha.getFullYear()
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${anio}-${mes}-${dia}`
}

export function sumarDias(fecha: Date, cantidad: number): Date {
  return new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate() + cantidad)
}

export function inicioSemana(fecha: Date): Date {
  return sumarDias(fecha, -((fecha.getDay() + 6) % 7))
}

export function fechasVisibles(fecha: Date, vista: VistaCalendario): Date[] {
  if (vista === 'lista') {
    const ultimoDia = new Date(fecha.getFullYear(), fecha.getMonth() + 1, 0).getDate()
    return Array.from(
      { length: ultimoDia },
      (_, indice) => new Date(fecha.getFullYear(), fecha.getMonth(), indice + 1),
    )
  }
  if (vista === 'mes') {
    const primerDia = new Date(fecha.getFullYear(), fecha.getMonth(), 1)
    const inicio = inicioSemana(primerDia)
    const ultimoDia = new Date(fecha.getFullYear(), fecha.getMonth() + 1, 0)
    const semanas = Math.ceil((((primerDia.getDay() + 6) % 7) + ultimoDia.getDate()) / 7)
    return Array.from({ length: semanas * 7 }, (_, indice) => sumarDias(inicio, indice))
  }
  const inicio = inicioSemana(fecha)
  return Array.from({ length: 7 }, (_, indice) => sumarDias(inicio, indice))
}

export function tituloPeriodo(fecha: Date, vista: VistaCalendario): string {
  if (vista !== 'semana') {
    const texto = new Intl.DateTimeFormat(idioma, { month: 'long', year: 'numeric' }).format(fecha)
    return texto.charAt(0).toUpperCase() + texto.slice(1)
  }
  const inicio = inicioSemana(fecha)
  const fin = sumarDias(inicio, 6)
  const mesInicio = new Intl.DateTimeFormat(idioma, { month: 'short' }).format(inicio)
  const mesFin = new Intl.DateTimeFormat(idioma, { month: 'short', year: 'numeric' }).format(fin)
  return `${inicio.getDate()} ${mesInicio} – ${fin.getDate()} ${mesFin}`
}

export function moverPeriodo(fecha: Date, vista: VistaCalendario, direccion: number): Date {
  if (vista === 'semana') return sumarDias(fecha, direccion * 7)
  const dia = fecha.getDate()
  const ultimo = new Date(fecha.getFullYear(), fecha.getMonth() + direccion + 1, 0).getDate()
  return new Date(fecha.getFullYear(), fecha.getMonth() + direccion, Math.min(dia, ultimo))
}

export function fechaLarga(fecha: Date): string {
  return new Intl.DateTimeFormat(idioma, { weekday: 'long', day: 'numeric', month: 'long' }).format(
    fecha,
  )
}
