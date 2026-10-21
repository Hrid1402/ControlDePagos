import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { configuracionUi } from '@/config/ui'
import RutaSuperficie from '@/components/ruta/RutaSuperficie.vue'
import { avance, lugarDe, pasoDe, textoTotal, type ItemRuta } from '@/components/ruta/modelo'

const item = (cambios: Partial<ItemRuta> = {}): ItemRuta => ({
  id: crypto.randomUUID(),
  empresa: 'Hidrandina',
  alias: null,
  codigo_suministro: '123',
  categoria: { id: 'c1', nombre: 'Luz', color: '#F59E0B', icono: 'pi-bolt', tipo: 'x' },
  monto: '85.40',
  saldo: '85.40',
  moneda: 'PEN',
  estado: 'pendiente',
  fecha_vencimiento: '2026-10-25',
  en_ruta: false,
  pago_realizado: false,
  pago_realizado_en: null,
  comprobante_estado: null,
  ...cambios,
})
const enRuta = { estado: 'en_proceso', en_ruta: true }

describe('diseño de la ruta de pagos (H23)', () => {
  it('distingue cada paso: declarada no es validada (TASK-80)', () => {
    expect(pasoDe(item())).toBe('disponible')
    expect(pasoDe(item({ estado: 'esperando_aprobacion' }))).toBe('espera_aprobacion')
    expect(pasoDe(item(enRuta))).toBe('por_pagar')
    expect(pasoDe(item({ ...enRuta, pago_realizado: true }))).toBe('declarada')
    expect(pasoDe(item({ ...enRuta, comprobante_estado: 'procesando' }))).toBe('validando')
    expect(pasoDe(item({ ...enRuta, comprobante_estado: 'rechazado' }))).toBe('rechazado')
  })

  it('suma lo que hay que llevar sin mezclar monedas (CA02)', () => {
    const lista = [item(), item({ saldo: '62.10' }), item({ saldo: '20.00', moneda: 'USD' })]
    const total = textoTotal(lista)
    expect(total).toContain('147.50')
    expect(total).toContain(' + ')
    expect(total).toContain('20.00')
    expect(lugarDe(null).titulo).toBe('Sin lugar registrado')
    expect(lugarDe('agente_kasnet').titulo).toBe('Agente KasNet')
  })

  it('al terminar recuerda los comprobantes que faltan (CA03, CA04)', () => {
    const declarada = item({ ...enRuta, pago_realizado: true })
    const pendiente = item(enRuta)
    const grupos = [
      { lugar: 'agente_bcp', items: [declarada, pendiente], totales: { PEN: '0', USD: '0' } },
    ]
    expect(avance(grupos).terminada).toBe(false)

    pendiente.pago_realizado = true
    const fin = avance(grupos)
    expect(fin.terminada).toBe(true)
    expect(fin.sinComprobante).toHaveLength(2)

    const vista = mount(RutaSuperficie, {
      props: { ruta: { grupos, totales: { PEN: '0', USD: '0' } }, hoy: '2026-10-20' },
      global: { plugins: [[PrimeVue, configuracionUi]] },
    })
    expect(vista.text()).toContain('Terminaste la ruta')
    expect(vista.text()).toContain('faltan 2')
    expect(
      vista.findAll('button').filter((b) => b.text().includes('Adjuntar comprobante')),
    ).toHaveLength(2)
  })

  it('muestra qué deudas del lote no se iniciaron y por qué', () => {
    const luz = item({ alias: 'Luz de la casa' })
    const visa = item({ alias: 'Tarjeta Visa' })
    const vista = mount(RutaSuperficie, {
      props: {
        ruta: {
          grupos: [{ lugar: null, items: [luz, visa], totales: { PEN: '0', USD: '0' } }],
          totales: { PEN: '0', USD: '0' },
        },
        hoy: '2026-10-20',
        resultados: [
          { deuda_id: luz.id, resultado: 'iniciada', codigo: null, mensaje: null, repetido: false },
          {
            deuda_id: visa.id,
            resultado: 'conflicto',
            codigo: 'PAGO_EN_CURSO',
            mensaje: 'Otra persona ya está pagando esta deuda.',
            repetido: false,
          },
        ],
      },
      global: { plugins: [[PrimeVue, configuracionUi]] },
    })
    expect(vista.text()).toContain('Iniciaste 1 pago')
    expect(vista.text()).toContain('Tarjeta Visa · Otra persona ya está pagando esta deuda.')
  })
})
