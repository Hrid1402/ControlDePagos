export interface EventoTiempoReal {
  tipo: string
  datos?: Record<string, unknown>
  id?: string
}
export function crearCanal(opciones: {
  obtenerToken: () => string | null
  alInvalidar: (motivo: string) => void
  alResincronizar: () => void
}) {
  const conexiones = new Set<WebSocket>()
  const oyentes = new Set<(evento: EventoTiempoReal) => void>()
  let actual: WebSocket | null = null
  let reintento: ReturnType<typeof setTimeout> | undefined
  let plazo: ReturnType<typeof setTimeout> | undefined
  let espera = 1000
  let detenido = false
  function desconectar() {
    clearTimeout(reintento)
    clearTimeout(plazo)
    conexiones.forEach((socket) => socket.close())
    conexiones.clear()
    actual = null
  }
  function conectar(token: string) {
    clearTimeout(reintento)
    clearTimeout(plazo)
    detenido = false
    // Conserva el socket autenticado anterior hasta recibir conectado en el nuevo.
    conexiones.forEach((socket) => {
      if (socket !== actual) {
        socket.close()
        conexiones.delete(socket)
      }
    })
    const url = new URL(`${import.meta.env.VITE_API_URL || '/api/v1'}/ws`, window.location.origin)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(url.href)
    conexiones.add(socket)
    const vigente = () => !detenido && opciones.obtenerToken() === token && conexiones.has(socket)
    plazo = setTimeout(() => {
      if (socket !== actual) socket.close()
    }, 10000)
    socket.onopen = () => {
      if (vigente()) socket.send(JSON.stringify({ tipo: 'autenticar', token }))
    }
    socket.onmessage = (mensaje) => {
      if (!vigente()) return
      let evento: EventoTiempoReal
      try {
        evento = JSON.parse(mensaje.data)
      } catch {
        return
      }
      if (!evento || typeof evento.tipo !== 'string') return
      if (evento.tipo === 'sesion_cerrada') {
        opciones.alInvalidar(
          typeof evento.datos?.code === 'string' ? evento.datos.code : 'NO_AUTENTICADO',
        )
        return
      }
      if (evento.tipo === 'conectado') {
        clearTimeout(plazo)
        espera = 1000
        actual = socket
        conexiones.forEach((anterior) => {
          if (anterior !== socket) {
            conexiones.delete(anterior)
            anterior.close()
          }
        })
      }
      if (evento.tipo === 'conectado' || evento.tipo === 'resincronizar') opciones.alResincronizar()
      oyentes.forEach((escuchar) => escuchar(evento))
    }
    socket.onclose = (evento) => {
      const eraVigente = vigente()
      conexiones.delete(socket)
      if (actual === socket) actual = null
      if (!eraVigente) return
      clearTimeout(plazo)
      if (evento.code === 4401) {
        opciones.alInvalidar(evento.reason || 'NO_AUTENTICADO')
        return
      }
      reintento = setTimeout(() => {
        if (opciones.obtenerToken() === token && !detenido) conectar(token)
      }, espera)
      espera = Math.min(espera * 2, 30000)
    }
  }
  return {
    conectar,
    detener() {
      detenido = true
      desconectar()
    },
    suscribir(escuchar: (evento: EventoTiempoReal) => void) {
      oyentes.add(escuchar)
      return () => oyentes.delete(escuchar)
    },
  }
}
