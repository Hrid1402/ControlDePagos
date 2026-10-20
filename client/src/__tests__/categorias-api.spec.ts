import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  crearCategoria,
  editarCategoria,
  eliminarCategoria,
  listarCategorias,
} from '@/api/categorias'

const http = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }))
vi.mock('@/api/http', () => ({ http }))

const datos = { nombre: 'Colegio', tipo: 'monto_fijo', color: '#2563EB', icono: 'pi-tag' } as const

beforeEach(() => Object.values(http).forEach((f) => f.mockReset()))

describe('cliente de categorías', () => {
  it('lista, crea y edita', async () => {
    http.get.mockResolvedValueOnce({ data: [] })
    http.post.mockResolvedValueOnce({ data: { id: 'c1' } })
    http.put.mockResolvedValueOnce({ data: { id: 'c1' } })

    await listarCategorias()
    await crearCategoria(datos)
    await editarCategoria('c1', datos)

    expect(http.get).toHaveBeenCalledWith('/categorias')
    expect(http.post).toHaveBeenCalledWith('/categorias', datos)
    expect(http.put).toHaveBeenCalledWith('/categorias/c1', datos)
  })

  it('al eliminar envía el destino solo si lo hay (CA05)', async () => {
    http.delete.mockResolvedValue({ data: { servicios_movidos: 2 } })

    expect(await eliminarCategoria('c1', 'c2')).toBe(2)
    await eliminarCategoria('c3')

    expect(http.delete).toHaveBeenNthCalledWith(1, '/categorias/c1', {
      params: { mover_a: 'c2' },
    })
    expect(http.delete).toHaveBeenNthCalledWith(2, '/categorias/c3', { params: undefined })
  })
})
