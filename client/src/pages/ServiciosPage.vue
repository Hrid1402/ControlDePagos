<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import ServiciosSuperficie from '@/components/servicios/ServiciosSuperficie.vue'
import FormularioServicio from '@/components/servicios/FormularioServicio.vue'
import DialogoBajaServicio from '@/components/servicios/DialogoBajaServicio.vue'
import {
  nombreServicio,
  type CategoriaServicio,
  type DatosServicio,
  type Empresa,
  type FiltroEstado,
  type Servicio,
  type ServicioDetalle,
} from '@/components/servicios/modelo'
import {
  crearServicio,
  darDeBajaServicio,
  editarServicio,
  listarEmpresas,
  listarServicios,
  obtenerServicio,
  reactivarServicio,
  type FiltrosServicios,
} from '@/api/servicios'
import { listarCategorias } from '@/api/categorias'
import { useSesionStore } from '@/stores/sesion'
import type { ErrorApi } from '@/types/api'

// H10 (TASK-34): lista con búsqueda y filtros (CA10) y el formulario de servicio (CA01 a CA07).
// Gerente y asistente registran y editan en cualquier categoría (CA09); solo el gerente da de
// baja y reactiva (CA08). Los filtros viven en la URL: se comparten y sobreviven a recargar.
const route = useRoute()
const router = useRouter()
const toast = useToast()
const sesion = useSesionStore()

const servicios = ref<Servicio[]>([])
const total = ref(0)
const pagina = ref(1)
const estado = ref<'cargando' | 'lista' | 'error'>('cargando')
const cargandoMas = ref(false)
const categorias = ref<CategoriaServicio[]>([])
const empresas = ref<Empresa[]>([])
const formulario = ref<{ servicio: ServicioDetalle | null } | null>(null)
const bajando = ref<ServicioDetalle | null>(null)
const ocupado = ref<string | null>(null)
let solicitud: AbortController | null = null

const esGerente = computed(() => sesion.usuario?.rol === 'gerente')
const texto = (valor: unknown) => (typeof valor === 'string' ? valor : '')
const ESTADOS: FiltroEstado[] = ['activo', 'baja', 'todos']
const filtros = computed<FiltrosServicios>(() => {
  const pedido = texto(route.query.estado) as FiltroEstado
  return {
    q: texto(route.query.q),
    categoria_id: texto(route.query.categoria),
    estado: ESTADOS.includes(pedido) ? pedido : 'activo',
  }
})

// Cada cambio parte de la URL que dejó el anterior: dos filtros cambiados seguidos se conservan.
let navegacion: Promise<unknown> = Promise.resolve()
function navegar(campo: 'q' | 'categoria' | 'estado', valor: string) {
  navegacion = navegacion.then(() => {
    const query = { ...route.query, [campo]: valor }
    if (query.estado === 'activo') delete query.estado
    return router.replace({
      query: Object.fromEntries(Object.entries(query).filter(([, v]) => v)),
    })
  })
}

const fallo = (error: unknown, mensaje: string) => (error as ErrorApi).detail || mensaje

async function cargar() {
  solicitud?.abort()
  const actual = new AbortController()
  solicitud = actual
  estado.value = 'cargando'
  try {
    const respuesta = await listarServicios(filtros.value, 1, actual.signal)
    servicios.value = respuesta.items
    total.value = respuesta.total
    pagina.value = 1
    estado.value = 'lista'
  } catch {
    if (actual.signal.aborted) return
    servicios.value = []
    estado.value = 'error'
  }
}

async function mostrarMas() {
  if (cargandoMas.value) return
  cargandoMas.value = true
  try {
    const respuesta = await listarServicios(filtros.value, pagina.value + 1)
    // Si se registró un servicio entre páginas, uno puede repetirse: se muestra una vez.
    const vistos = new Set(servicios.value.map((s) => s.id))
    servicios.value.push(...respuesta.items.filter((s) => !vistos.has(s.id)))
    total.value = respuesta.total
    pagina.value += 1
  } catch {
    toast.add({
      severity: 'error',
      summary: 'No pudimos cargar más servicios',
      detail: 'Inténtalo otra vez.',
      life: 5000,
    })
  } finally {
    cargandoMas.value = false
  }
}

/** Categorías y empresas del formulario: sin ellas la lista sigue sirviendo. */
async function cargarCatalogos() {
  const [cats, emps] = await Promise.allSettled([listarCategorias(), listarEmpresas()])
  if (cats.status === 'fulfilled') categorias.value = cats.value
  if (emps.status === 'fulfilled') empresas.value = emps.value
}

/** Abre el detalle antes de editar o dar de baja: trae las deudas pendientes al día. */
async function conDetalle(id: string, abrir: (detalle: ServicioDetalle) => void) {
  if (ocupado.value) return
  ocupado.value = id
  try {
    abrir(await obtenerServicio(id))
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'No pudimos abrir el servicio',
      detail: fallo(error, 'Inténtalo otra vez.'),
      life: 5000,
    })
    if ((error as ErrorApi).status === 404) await cargar()
  } finally {
    ocupado.value = null
  }
}

/** El formulario ya confirma que se guardó; aquí solo se suma la advertencia de CA07. */
async function guardar(datos: DatosServicio) {
  const editado = formulario.value?.servicio
  if (editado) {
    const respuesta = await editarServicio(editado.id, datos)
    const { codigo_cambiado, deudas_pendientes } = respuesta.advertencias
    if (codigo_cambiado && deudas_pendientes) {
      toast.add({
        severity: 'warn',
        summary: 'Revisa sus deudas pendientes',
        detail: `${nombreServicio(respuesta)} tiene ${
          deudas_pendientes === 1 ? '1 deuda pendiente' : `${deudas_pendientes} deudas pendientes`
        } registradas con el código anterior.`,
        life: 8000,
      })
    }
  } else {
    await crearServicio(datos)
  }
  formulario.value = null
  await cargar()
}

async function confirmarBaja() {
  const servicio = bajando.value
  if (!servicio) return
  await darDeBajaServicio(servicio.id)
  bajando.value = null
  toast.add({
    severity: 'success',
    summary: 'Servicio dado de baja',
    detail: `${nombreServicio(servicio)} ya no genera deudas nuevas.`,
    life: 5000,
  })
  await cargar()
}

async function reactivar(id: string) {
  if (ocupado.value) return
  ocupado.value = id
  try {
    const servicio = await reactivarServicio(id)
    toast.add({
      severity: 'success',
      summary: 'Servicio reactivado',
      detail: `${nombreServicio(servicio)} volvió a tu lista de activos.`,
      life: 4000,
    })
    await cargar()
  } catch (error) {
    toast.add({
      severity: 'error',
      summary: 'No pudimos reactivarlo',
      detail: fallo(error, 'Inténtalo otra vez.'),
      life: 5000,
    })
  } finally {
    ocupado.value = null
  }
}

watch(() => route.query, cargar, { immediate: true })
onMounted(cargarCatalogos)
onBeforeUnmount(() => solicitud?.abort())
</script>

<template>
  <div class="pagina-servicios">
    <ServiciosSuperficie
      :servicios="servicios"
      :total="total"
      :categorias="categorias"
      :busqueda="filtros.q"
      :categoria="filtros.categoria_id"
      :estado="filtros.estado"
      :estado-pantalla="estado"
      :hay-mas="servicios.length < total"
      :cargando-mas="cargandoMas"
      :puede-dar-de-baja="esGerente"
      :ocupado="ocupado"
      @buscar="navegar('q', $event)"
      @filtrar-categoria="navegar('categoria', $event)"
      @filtrar-estado="navegar('estado', $event)"
      @crear="formulario = { servicio: null }"
      @editar="conDetalle($event, (servicio) => (formulario = { servicio }))"
      @baja="conDetalle($event, (servicio) => (bajando = servicio))"
      @reactivar="reactivar"
      @reintentar="cargar"
      @mas="mostrarMas"
    />
    <FormularioServicio
      v-if="formulario"
      :servicio="formulario.servicio"
      :empresas="empresas"
      :categorias="categorias"
      :guardar="guardar"
      @cerrar="formulario = null"
    />
    <DialogoBajaServicio
      v-if="bajando"
      :servicio="bajando"
      :confirmar="confirmarBaja"
      @cerrar="bajando = null"
    />
  </div>
</template>

<style scoped>
.pagina-servicios {
  max-width: 1120px;
}
</style>
