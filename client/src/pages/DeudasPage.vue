<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import DeudasSuperficie from '@/components/deudas/DeudasSuperficie.vue'
import FormularioDeuda from '@/components/deudas/FormularioDeuda.vue'
import {
  filtrosDeQuery,
  queryDeFiltros,
  type CategoriaDeuda,
  type FiltrosDeudas,
  type ItemDeuda,
  type Totales,
} from '@/components/deudas/listado'
import { hoyEnLima } from '@/components/deudas/modelo'
import type { Servicio } from '@/components/servicios/modelo'
import { listarDeudas } from '@/api/deudas'
import { useRegistroDeuda } from '@/composables/useRegistroDeuda'
import { listarCategorias } from '@/api/categorias'
import { listarServicios } from '@/api/servicios'
import { useSesionStore } from '@/stores/sesion'
import type { ErrorApi } from '@/types/api'

// H36 con datos reales (TASK-46). Los filtros viven en la URL: se conservan al volver del detalle
// (CA09) y el panel puede abrir la lista ya filtrada (CA13).
const route = useRoute()
const router = useRouter()
const toast = useToast()
const sesion = useSesionStore()

const items = ref<ItemDeuda[]>([])
const total = ref(0)
const totales = ref<Totales | null>(null)
const categorias = ref<CategoriaDeuda[]>([])
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('cargando')
const filtros = computed(() => filtrosDeQuery(route.query))

let solicitud: AbortController | null = null
async function cargar() {
  solicitud?.abort()
  const actual = new AbortController()
  solicitud = actual
  estadoPantalla.value = 'cargando'
  try {
    const pagina = await listarDeudas(filtros.value, actual.signal)
    items.value = pagina.items
    total.value = pagina.total
    totales.value = pagina.totales
    estadoPantalla.value = 'lista'
  } catch (fallo) {
    if (actual.signal.aborted) return
    // Una categoría que ya no existe deja la lista vacía en lugar de un error.
    if ((fallo as ErrorApi).status === 404 && filtros.value.categoria)
      return filtrar({ categoria: '' })
    estadoPantalla.value = 'error'
  }
}

watch(() => route.query, cargar, { immediate: true })
onMounted(async () => {
  try {
    categorias.value = await listarCategorias()
  } catch {
    categorias.value = []
  }
})
onBeforeUnmount(() => solicitud?.abort())

function filtrar(cambios: Partial<FiltrosDeudas>) {
  return router.replace({ query: queryDeFiltros({ ...filtros.value, ...cambios }) })
}

function abrir(id: string) {
  void router.push({ name: `${sesion.rol}-deuda`, params: { id } })
}

// Registrar deuda (CA12): el formulario de H11 con los servicios activos del gerente.
const registrando = ref(false)
const servicios = ref<Servicio[]>([])
const { registrar, duplicada } = useRegistroDeuda(async () => {
  registrando.value = false
  await cargar()
})

async function abrirRegistro() {
  duplicada.value = null
  try {
    const todos: Servicio[] = []
    for (let pagina = 1; ; pagina++) {
      const respuesta = await listarServicios({ q: '', categoria_id: '', estado: 'activo' }, pagina)
      todos.push(...respuesta.items)
      if (todos.length >= respuesta.total || !respuesta.items.length) break
    }
    servicios.value = todos
    registrando.value = true
  } catch (fallo) {
    toast.add({
      severity: 'error',
      summary: 'No se pudo abrir',
      detail: (fallo as ErrorApi).detail,
      life: 5000,
    })
  }
}
</script>

<template>
  <DeudasSuperficie
    :items="items"
    :total="total"
    :totales="totales"
    :categorias="categorias"
    :filtros="filtros"
    :estado-pantalla="estadoPantalla"
    :hoy="hoyEnLima()"
    @filtrar="filtrar"
    @limpiar="
      router.replace({ query: queryDeFiltros({ ...filtrosDeQuery({}), orden: filtros.orden }) })
    "
    @abrir="abrir"
    @registrar="abrirRegistro"
    @registrar-servicio="router.push({ name: `${sesion.rol}-servicios` })"
    @reintentar="cargar"
  />
  <FormularioDeuda
    v-if="registrando"
    :servicios="servicios"
    :guardar="registrar"
    :duplicada="duplicada"
    @cerrar="registrando = false"
    @ver-duplicada="abrir"
  />
</template>
