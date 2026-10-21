<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import BandejaSuperficie from '@/components/bandeja/BandejaSuperficie.vue'
import {
  consultaDeQuery,
  queryDeConsulta,
  type Contadores,
  type ItemBandeja,
  type Pestana,
} from '@/components/bandeja/modelo'
import type { CategoriaDeuda } from '@/components/deudas/listado'
import { hoyEnLima } from '@/components/deudas/modelo'
import { fijarDeuda, obtenerBandejaCompleta, recordarManana } from '@/api/bandeja'
import { listarCategorias } from '@/api/categorias'
import { useSesionStore } from '@/stores/sesion'
import type { ErrorApi } from '@/types/api'

// H15 con datos reales (TASK-50): la pantalla de inicio de la asistente (CA01). La pestaña y la
// categoría viven en la URL, así se conservan al volver del detalle de una deuda.
const route = useRoute()
const router = useRouter()
const toast = useToast()
const sesion = useSesionStore()

const items = ref<ItemBandeja[]>([])
const contadores = ref<Contadores>({ por_pagar: 0, por_validar: 0, rechazadas: 0 })
const categorias = ref<CategoriaDeuda[]>([])
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('cargando')
const seleccion = ref<string[]>([])
/** La deuda con una acción en curso: sus botones se desactivan hasta que termine. */
const ocupado = ref<string | null>(null)
const consulta = computed(() => consultaDeQuery(route.query))

let solicitud: AbortController | null = null
/** Silenciosa: después de una acción, sin volver a mostrar el estado de carga. */
async function cargar(silenciosa = false) {
  solicitud?.abort()
  const actual = new AbortController()
  solicitud = actual
  if (!silenciosa) estadoPantalla.value = 'cargando'
  try {
    const bandeja = await obtenerBandejaCompleta(consulta.value, actual.signal)
    items.value = bandeja.items
    contadores.value = bandeja.contadores
    // Lo seleccionado que ya no está (pagado, pospuesto o tomado por otro) sale de la selección.
    seleccion.value = seleccion.value.filter((id) => bandeja.items.some((i) => i.id === id))
    estadoPantalla.value = 'lista'
  } catch (fallo) {
    if (actual.signal.aborted) return
    // Una categoría que ya no existe vuelve a «Todas» en lugar de mostrar un error.
    if ((fallo as ErrorApi).status === 404 && consulta.value.categoria)
      return filtrar({ categoria: '' })
    if (!silenciosa) estadoPantalla.value = 'error'
  }
}

watch(
  () => route.query,
  () => {
    seleccion.value = []
    void cargar()
  },
  { immediate: true },
)
onMounted(async () => {
  try {
    categorias.value = await listarCategorias()
  } catch {
    categorias.value = []
  }
})
onBeforeUnmount(() => solicitud?.abort())

function filtrar(cambios: Partial<{ pestana: Pestana; categoria: string }>) {
  return router.replace({ query: queryDeConsulta({ ...consulta.value, ...cambios }) })
}

function abrir(id: string) {
  void router.push({ name: `${sesion.rol}-deuda`, params: { id } })
}

function avisarError(fallo: unknown) {
  toast.add({
    severity: 'error',
    summary: 'No se pudo completar',
    detail: (fallo as ErrorApi).detail,
    life: 6000,
  })
}

/** Ejecuta la acción de una deuda y vuelve a pedir la bandeja: el orden lo decide el backend. */
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

// CA07: fijada sube arriba, después de las órdenes urgentes.
function fijar(id: string, valor: boolean) {
  return ejecutar(id, async () => {
    await fijarDeuda(id, valor)
  })
}

// CA08: desaparece hasta las 08:00 de mañana. Con una orden urgente abierta el backend responde
// 409 y el aviso lo explica.
function posponer(id: string) {
  return ejecutar(id, async () => {
    await recordarManana(id)
    seleccion.value = seleccion.value.filter((s) => s !== id)
    toast.add({
      severity: 'success',
      summary: 'Te la recordamos mañana',
      detail: 'Vuelve a la bandeja mañana a las 8:00.',
      life: 4000,
    })
  })
}
</script>

<template>
  <BandejaSuperficie
    :items="items"
    :contadores="contadores"
    :pestana="consulta.pestana"
    :categoria="consulta.categoria"
    :categorias="categorias"
    :estado-pantalla="estadoPantalla"
    :hoy="hoyEnLima()"
    :seleccion="seleccion"
    :usuario-id="sesion.usuario?.id"
    :nombre="sesion.usuario?.nombre"
    :ocupado="ocupado"
    @cambiar-pestana="filtrar({ pestana: $event })"
    @filtrar-categoria="filtrar({ categoria: $event })"
    @seleccionar="seleccion = $event"
    @abrir="abrir"
    @fijar="fijar"
    @posponer="posponer"
    @reintentar="cargar()"
  />
</template>
