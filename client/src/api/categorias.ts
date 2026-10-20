import { http } from './http'
import type { Categoria, TipoCategoria } from '@/components/categorias/modelo'

// Categorías del gerente (H09). La asistente también puede listar y crear (CA04).

export interface DatosCategoria {
  nombre: string
  tipo: TipoCategoria
  color: string
  icono: string
}

export async function listarCategorias(): Promise<Categoria[]> {
  const { data } = await http.get<Categoria[]>('/categorias')
  return data
}

export async function crearCategoria(datos: DatosCategoria): Promise<Categoria> {
  const { data } = await http.post<Categoria>('/categorias', datos)
  return data
}

export async function editarCategoria(id: string, datos: DatosCategoria): Promise<Categoria> {
  const { data } = await http.put<Categoria>(`/categorias/${id}`, datos)
  return data
}

/** Con servicios, mover_a indica a qué categoría pasan antes de eliminarla (CA05). */
export async function eliminarCategoria(id: string, moverA?: string): Promise<number> {
  const { data } = await http.delete<{ servicios_movidos: number }>(`/categorias/${id}`, {
    params: moverA ? { mover_a: moverA } : undefined,
  })
  return data.servicios_movidos
}
