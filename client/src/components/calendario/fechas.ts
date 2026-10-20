const idioma = 'es-PE'

export function hoyLima(): string {
  const partes = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Lima',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date())
  const dato = (tipo: string) => partes.find((parte) => parte.type === tipo)?.value || ''
  return `${dato('year')}-${dato('month')}-${dato('day')}`
}

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

export function fechaLarga(fecha: Date): string {
  return new Intl.DateTimeFormat(idioma, { weekday: 'long', day: 'numeric', month: 'long' }).format(
    fecha,
  )
}
