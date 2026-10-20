import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { crearCanal } from '@/services/tiempoReal'

class Socket {
  static instancias: Socket[] = []
  onopen?: () => void
  onmessage?: (evento: { data: string }) => void
  onclose?: (evento: { code: number; reason: string }) => void
  send = vi.fn()
  close = vi.fn()
  constructor(public url: string) {
    Socket.instancias.push(this)
  }
  mensaje(evento: unknown) {
    this.onmessage?.({ data: JSON.stringify(evento) })
  }
  cerrar(code = 1006, reason = '') {
    this.onclose?.({ code, reason })
  }
}
let token: string | null
let invalidar: ReturnType<typeof vi.fn<(motivo: string) => void>>
let resincronizar: ReturnType<typeof vi.fn<() => void>>
let canal: ReturnType<typeof crearCanal>
beforeEach(() => {
  vi.useFakeTimers()
  Socket.instancias = []
  vi.stubGlobal('WebSocket', Socket)
  token = 'primero'
  invalidar = vi.fn()
  resincronizar = vi.fn()
  canal = crearCanal({
    obtenerToken: () => token,
    alInvalidar: invalidar,
    alResincronizar: resincronizar,
  })
})
afterEach(() => {
  canal.detener()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
describe('canal autenticado y renovación', () => {
  it('envía la credencial como primer mensaje y recupera pendientes al conectar o resincronizar', () => {
    const escuchar = vi.fn()
    const quitar = canal.suscribir(escuchar)
    canal.conectar(token!)
    const s = Socket.instancias[0]!
    expect(s.url).toContain('/api/v1/ws')
    expect(s.url).not.toContain(token!)
    s.onopen?.()
    expect(s.send).toHaveBeenCalledWith(JSON.stringify({ tipo: 'autenticar', token }))
    s.mensaje({ tipo: 'conectado' })
    s.mensaje({ tipo: 'resincronizar' })
    expect(resincronizar).toHaveBeenCalledTimes(2)
    s.mensaje({ tipo: 'orden_nueva', datos: { id: '1' } })
    expect(escuchar).toHaveBeenLastCalledWith({ tipo: 'orden_nueva', datos: { id: '1' } })
    quitar()
    s.mensaje({ tipo: 'notificacion' })
    expect(escuchar).toHaveBeenCalledTimes(3)
  })
  it('espera conectado antes de cerrar el canal anterior e ignora su vencimiento tardío', () => {
    canal.conectar(token!)
    const anterior = Socket.instancias[0]!
    anterior.mensaje({ tipo: 'conectado' })
    token = 'renovado'
    canal.conectar(token)
    const nuevo = Socket.instancias[1]!
    expect(anterior.close).not.toHaveBeenCalled()
    anterior.mensaje({ tipo: 'sesion_cerrada', datos: { code: 'NO_AUTENTICADO' } })
    anterior.cerrar(4401, 'NO_AUTENTICADO')
    expect(invalidar).not.toHaveBeenCalled()
    nuevo.mensaje({ tipo: 'conectado' })
    expect(resincronizar).toHaveBeenCalledTimes(2)
  })
  it('reemplaza y cierra el socket anterior cuando el nuevo confirma', () => {
    canal.conectar(token!)
    const anterior = Socket.instancias[0]!
    anterior.mensaje({ tipo: 'conectado' })
    token = 'segundo'
    canal.conectar(token)
    Socket.instancias[1]!.mensaje({ tipo: 'conectado' })
    expect(anterior.close).toHaveBeenCalledOnce()
    anterior.cerrar(4401, 'SESION_REVOCADA')
    expect(invalidar).not.toHaveBeenCalled()
  })
  it.each(['SESION_REVOCADA', 'CUENTA_INACTIVA', 'NO_AUTENTICADO'])(
    'respeta el cierre vigente por %s',
    (motivo) => {
      canal.conectar(token!)
      Socket.instancias[0]!.cerrar(4401, motivo)
      expect(invalidar).toHaveBeenCalledWith(motivo)
      vi.advanceTimersByTime(60000)
      expect(Socket.instancias).toHaveLength(1)
    },
  )
  it('respeta el evento de cierre y completa un motivo ausente', () => {
    canal.conectar(token!)
    Socket.instancias[0]!.mensaje({ tipo: 'sesion_cerrada' })
    expect(invalidar).toHaveBeenCalledWith('NO_AUTENTICADO')
  })
  it('reconecta con espera creciente y detiene los reintentos al cerrar sesión', () => {
    canal.conectar(token!)
    Socket.instancias[0]!.cerrar()
    vi.advanceTimersByTime(999)
    expect(Socket.instancias).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(Socket.instancias).toHaveLength(2)
    Socket.instancias[1]!.cerrar()
    vi.advanceTimersByTime(2000)
    expect(Socket.instancias).toHaveLength(3)
    Socket.instancias[2]!.cerrar()
    canal.detener()
    vi.advanceTimersByTime(60000)
    expect(Socket.instancias).toHaveLength(3)
  })
  it('descarta mensajes inválidos y cierra una autenticación que no responde', () => {
    canal.conectar(token!)
    const s = Socket.instancias[0]!
    s.onmessage?.({ data: '{roto' })
    s.mensaje(null)
    s.mensaje({ tipo: 1 })
    vi.advanceTimersByTime(10000)
    expect(s.close).toHaveBeenCalled()
    expect(invalidar).not.toHaveBeenCalled()
    expect(resincronizar).not.toHaveBeenCalled()
  })
  it('reemplaza una autenticación pendiente y no envía tokens de sesiones anteriores', () => {
    canal.conectar(token!)
    const anterior = Socket.instancias[0]!
    token = 'nuevo'
    canal.conectar(token)
    anterior.onopen?.()
    expect(anterior.close).toHaveBeenCalled()
    expect(anterior.send).not.toHaveBeenCalled()
    token = null
    Socket.instancias[1]!.cerrar()
    vi.advanceTimersByTime(60000)
    expect(Socket.instancias).toHaveLength(2)
  })
})
