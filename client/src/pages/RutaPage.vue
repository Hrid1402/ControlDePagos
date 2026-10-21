<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import RutaSuperficie from '@/components/ruta/RutaSuperficie.vue'
import { pasoDe, type ResultadoDeuda, type Ruta } from '@/components/ruta/modelo'
import { hoyEnLima } from '@/components/deudas/modelo'
import { iniciarRuta, marcarPagada, obtenerRuta } from '@/api/ruta'
import { subirComprobante } from '@/api/comprobantes'
import type { ErrorApi } from '@/types/api'

// H23 con datos reales (TASK-80): la asistente elige qué pagar en persona, inicia la ruta, marca
// cada pago al avanzar y sube su voucher. Lo elegido en la bandeja llega en ?deudas=.
const route = useRoute()
const router = useRouter()
const toast = useToast()

const ruta = ref<Ruta | null>(null)
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('cargando')
const seleccion = ref<string[]>([])
const resultados = ref<ResultadoDeuda[] | null>(null)
const iniciando = ref(false)
const ocupado = ref<string | null>(null)

let solicitud: AbortController | null = null
async function cargar(silenciosa = false) {
  solicitud?.abort()
  const actual = new AbortController()
  solicitud = actual
  if (!silenciosa) estadoPantalla.value = 'cargando'
  try {
    ruta.value = await obtenerRuta(actual.signal)
    // Solo se puede elegir lo que sigue disponible.
    const disponibles = new Set(
      ruta.value.grupos
        .flatMap((g) => g.items)
        .filter((i) => pasoDe(i) === 'disponible')
        .map((i) => i.id),
    )
    seleccion.value = seleccion.value.filter((id) => disponibles.has(id))
    estadoPantalla.value = 'lista'
  } catch {
    if (actual.signal.aborted) return
    if (!silenciosa) estadoPantalla.value = 'error'
  }
}

// Lo que se eligió en la bandeja (CA12 de H15) llega una vez; luego la URL queda limpia.
const desdeBandeja = typeof route.query.deudas === 'string' ? route.query.deudas.split(',') : []
seleccion.value = desdeBandeja.filter(Boolean)
if (desdeBandeja.length) void router.replace({ query: {} })
void cargar()
onBeforeUnmount(() => solicitud?.abort())

function avisarError(fallo: unknown) {
  toast.add({
    severity: 'error',
    summary: 'No se pudo completar',
    detail: (fallo as ErrorApi).detail,
    life: 6000,
  })
}

// CA02: cada deuda trae su resultado; las que no se iniciaron se explican en la pantalla.
async function iniciar() {
  if (!seleccion.value.length) return
  iniciando.value = true
  try {
    const inicio = await iniciarRuta(seleccion.value)
    resultados.value = inicio.resultados
    seleccion.value = []
  } catch (fallo) {
    avisarError(fallo)
  } finally {
    iniciando.value = false
    await cargar(true)
  }
}

async function ejecutar(id: string, trabajo: () => Promise<void>) {
  ocupado.value = id
  try {
    await trabajo()
  } catch (fallo) {
    avisarError(fallo)
  } finally {
    await cargar(true)
    ocupado.value = null
  }
}

// CA03: la deuda queda pagada para la ruta, pero sigue por validar hasta que se valide su voucher.
function marcar(id: string) {
  return ejecutar(id, () => marcarPagada(id))
}

// CA04: el voucher se adjunta desde la misma ruta. Uno ya usado en otra deuda lo rechaza el
// backend con 409 DUPLICADO y su mensaje se muestra tal cual.
const selectorArchivo = ref<HTMLInputElement | null>(null)
let porAdjuntar: string | null = null

function elegirVoucher(id: string) {
  porAdjuntar = id
  selectorArchivo.value?.click()
}

async function adjuntar(evento: Event) {
  const entrada = evento.target as HTMLInputElement
  const archivo = entrada.files?.[0]
  entrada.value = ''
  const id = porAdjuntar
  porAdjuntar = null
  if (!archivo || !id) return
  await ejecutar(id, async () => {
    try {
      await subirComprobante(id, archivo)
    } catch (fallo) {
      if ((fallo as ErrorApi).code !== 'DUPLICADO') throw fallo
      toast.add({
        severity: 'warn',
        summary: 'Comprobante repetido',
        detail: (fallo as ErrorApi).detail,
        life: 8000,
      })
      return
    }
    toast.add({
      severity: 'success',
      summary: 'Voucher adjuntado',
      detail: 'Se está leyendo; después lo valida el gerente.',
      life: 5000,
    })
  })
}
</script>

<template>
  <RutaSuperficie
    :ruta="ruta"
    :estado-pantalla="estadoPantalla"
    :hoy="hoyEnLima()"
    :seleccion="seleccion"
    :ocupado="ocupado"
    :iniciando="iniciando"
    :resultados="resultados"
    @seleccionar="seleccion = $event"
    @iniciar="iniciar"
    @marcar="marcar"
    @adjuntar="elegirVoucher"
    @abrir="router.push({ name: 'asistente-deuda', params: { id: $event } })"
    @reintentar="cargar()"
    @cerrar-resultados="resultados = null"
    @ir-bandeja="router.push({ name: 'asistente-inicio' })"
  />
  <input
    ref="selectorArchivo"
    type="file"
    accept="application/pdf,image/jpeg,image/png"
    class="oculto"
    aria-label="Elegir el voucher"
    @change="adjuntar"
  />
</template>

<style scoped>
.oculto {
  display: none;
}
</style>
