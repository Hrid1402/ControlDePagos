import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import * as api from '@/api/deudas'
import { useRegistroDeuda } from '@/composables/useRegistroDeuda'
import { aDatos, valoresIniciales } from '@/components/deudas/modelo'

vi.mock('@/api/deudas', () => ({
  registrarDeuda: vi.fn(),
  crearPrestamo: vi.fn(),
  configurarRecurrencia: vi.fn(),
  subirRecibo: vi.fn(),
}))
const simulada = vi.mocked(api)

function usar() {
  const alRegistrar = vi.fn()
  let registro!: ReturnType<typeof useRegistroDeuda>
  mount(
    defineComponent({
      setup() {
        registro = useRegistroDeuda(alRegistrar)
        return () => null
      },
    }),
    { global: { plugins: [PrimeVue, ToastService] } },
  )
  return { registro, alRegistrar }
}

const datos = (cambios: Record<string, unknown>, tipo: Parameters<typeof aDatos>[1]) =>
  aDatos({ ...valoresIniciales('s1'), ...cambios }, tipo)

beforeEach(() => vi.resetAllMocks())

describe('registro de deuda por tipo (H11)', () => {
  it('un préstamo se registra con su cronograma', async () => {
    simulada.crearPrestamo.mockResolvedValue({ id: 'p1' })
    const { registro, alRegistrar } = usar()

    await registro.registrar(
      datos(
        { monto_total: '100', cuotas_total: '3', fecha_primera_cuota: '2027-01-31' },
        'prestamo',
      ),
    )

    expect(simulada.crearPrestamo).toHaveBeenCalled()
    expect(simulada.registrarDeuda).not.toHaveBeenCalled()
    expect(alRegistrar).toHaveBeenCalled()
  })

  it('un monto fijo que se repite configura la recurrencia con el día del vencimiento', async () => {
    simulada.registrarDeuda.mockResolvedValue({ id: 'd1' })
    const { registro } = usar()

    await registro.registrar(
      datos({ monto: '129.90', fecha_vencimiento: '2026-10-20', repetir: true }, 'monto_fijo'),
    )

    expect(simulada.configurarRecurrencia).toHaveBeenCalledWith('s1', {
      monto: '129.90',
      moneda: 'PEN',
      dia_emision: null,
      dia_vencimiento: 20,
      activa: true,
    })
  })

  it('si falla el recibo la deuda queda registrada y no se reintenta', async () => {
    simulada.registrarDeuda.mockResolvedValue({ id: 'd1' })
    simulada.subirRecibo.mockRejectedValue({ status: 503 })
    const { registro, alRegistrar } = usar()
    const recibo = new File(['x'], 'r.pdf', { type: 'application/pdf' })

    await registro.registrar(
      datos({ monto: '50', fecha_vencimiento: '2026-10-20', recibo }, 'servicio_variable'),
    )

    expect(alRegistrar).toHaveBeenCalled()
  })

  it('un duplicado deja la deuda existente para mostrarla', async () => {
    simulada.registrarDeuda.mockRejectedValue({
      status: 409,
      code: 'DUPLICADO',
      detail: 'Ya existe',
      field: 'periodo',
      datos: { deuda_existente: { id: 'd0' } },
    })
    const { registro } = usar()

    await expect(
      registro.registrar(
        datos({ monto: '50', fecha_vencimiento: '2026-10-20' }, 'servicio_variable'),
      ),
    ).rejects.toMatchObject({ code: 'DUPLICADO' })
    expect(registro.duplicada.value).toEqual({ id: 'd0' })
  })
})
