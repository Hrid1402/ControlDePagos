<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { useRouter } from 'vue-router'
import { useSesionStore } from '@/stores/sesion'
import {
  consultarCalendario,
  exportarCalendario,
  listarCategoriasCalendario,
} from '@/api/calendario'
import type { FiltrosCalendario } from '@/api/calendario'
import CalendarioSuperficie from '@/components/calendario/CalendarioSuperficie.vue'
import type {
  CategoriaCalendario,
  DiaCalendario,
  VencimientoCalendario,
} from '@/components/calendario/modelo'
import { fechaLarga, fechaLocal } from '@/components/calendario/fechas'
import type { ErrorApi } from '@/types/api'

const dias = ref<DiaCalendario[]>([])
const categorias = ref<CategoriaCalendario[]>([])
const errorCategorias = ref(false)
const filtros = ref<FiltrosCalendario | null>(null)
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('cargando')
const error = ref('')
const exportando = ref(false)
const errorExportacion = ref('')
const deudaSeleccionada = ref<VencimientoCalendario | null>(null)
let solicitud: AbortController | null = null

async function cargarCategorias() {
  try {
    categorias.value = await listarCategoriasCalendario()
    errorCategorias.value = false
  } catch {
    errorCategorias.value = true
  }
}
onMounted(() => {
  void cargarCategorias()
})
onBeforeUnmount(() => solicitud?.abort())

async function cargar(filtrosNuevos: FiltrosCalendario) {
  filtros.value = filtrosNuevos
  solicitud?.abort()
  const actual = new AbortController()
  solicitud = actual
  estadoPantalla.value = 'cargando'
  error.value = ''
  try {
    dias.value = await consultarCalendario(filtrosNuevos, actual.signal)
    estadoPantalla.value = 'lista'
  } catch (fallo) {
    if (actual.signal.aborted) return
    dias.value = []
    error.value = (fallo as ErrorApi).detail || 'Revisa tu conexión e inténtalo de nuevo.'
    estadoPantalla.value = 'error'
  }
}

function reintentar() {
  if (filtros.value) void cargar(filtros.value)
}

async function exportar() {
  if (!filtros.value || exportando.value) return
  exportando.value = true
  errorExportacion.value = ''
  try {
    const archivo = await exportarCalendario(filtros.value)
    const url = URL.createObjectURL(archivo)
    const enlace = document.createElement('a')
    enlace.href = url
    enlace.download = 'calendario.ics'
    document.body.append(enlace)
    enlace.click()
    enlace.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (fallo) {
    errorExportacion.value = (fallo as ErrorApi).detail || 'No pudimos exportar el calendario.'
  } finally {
    exportando.value = false
  }
}

function abrirDeuda(id: string) {
  deudaSeleccionada.value =
    dias.value.flatMap((dia) => dia.deudas).find((deuda) => deuda.id === id) || null
}

const router = useRouter()
const sesion = useSesionStore()
/** H16 CA: desde el vencimiento se abre el detalle de la deuda (H17). */
function verDeuda(id: string) {
  deudaSeleccionada.value = null
  void router.push({ name: `${sesion.rol}-deuda`, params: { id } })
}
function moneda(valor: string, codigo: string) {
  return `${codigo === 'PEN' ? 'S/' : '$'} ${valor}`
}
</script>

<template>
  <CalendarioSuperficie
    :dias="dias"
    :categorias="categorias"
    :estado-pantalla="estadoPantalla"
    :mensaje-error="error"
    :exportable="!!filtros && estadoPantalla === 'lista' && !exportando"
    :exportando="exportando"
    @consultar="cargar"
    @reintentar="reintentar"
    @exportar="exportar"
    @abrir-deuda="abrirDeuda"
  />
  <p v-if="errorCategorias" class="error-exportacion" role="alert">
    No pudimos cargar las categorías.
    <button type="button" @click="cargarCategorias">Reintentar</button>
  </p>
  <p v-if="errorExportacion" class="error-exportacion" role="alert">{{ errorExportacion }}</p>
  <Dialog
    :visible="!!deudaSeleccionada"
    modal
    :draggable="false"
    header="Detalle del vencimiento"
    :style="{ width: 'min(480px, calc(100vw - 24px))' }"
    @update:visible="deudaSeleccionada = null"
  >
    <dl v-if="deudaSeleccionada" class="datos-deuda">
      <div>
        <dt>Servicio</dt>
        <dd>{{ deudaSeleccionada.nombre }}</dd>
      </div>
      <div>
        <dt>Vence</dt>
        <dd>{{ fechaLarga(fechaLocal(deudaSeleccionada.fecha_vencimiento)) }}</dd>
      </div>
      <div>
        <dt>Estado</dt>
        <dd>{{ deudaSeleccionada.estado.replace(/_/g, ' ') }}</dd>
      </div>
      <div v-if="deudaSeleccionada.monto">
        <dt>Importe confirmado</dt>
        <dd>{{ moneda(deudaSeleccionada.monto, deudaSeleccionada.moneda) }}</dd>
      </div>
      <div v-else-if="deudaSeleccionada.monto_proyectado">
        <dt>Proyección sin recibo</dt>
        <dd>{{ moneda(deudaSeleccionada.monto_proyectado, deudaSeleccionada.moneda) }}</dd>
      </div>
      <div v-else>
        <dt>Importe</dt>
        <dd>Por confirmar</dd>
      </div>
    </dl>
    <template #footer>
      <Button
        v-if="deudaSeleccionada"
        label="Ver la deuda completa"
        icon="pi pi-arrow-right"
        icon-pos="right"
        @click="verDeuda(deudaSeleccionada.id)"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.error-exportacion {
  max-width: 1500px;
  margin: 16px auto 0;
  color: var(--deconsta-error);
}
.error-exportacion button {
  margin-left: 8px;
  border: 0;
  background: transparent;
  color: var(--deconsta-primary);
  font-weight: 700;
  text-decoration: underline;
  cursor: pointer;
}
.datos-deuda {
  margin: 0;
}
.datos-deuda div {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 13px 0;
  border-bottom: 1px solid #d6e1db;
}
.datos-deuda div:last-child {
  border-bottom: 0;
}
.datos-deuda dt {
  color: var(--deconsta-muted);
}
.datos-deuda dd {
  margin: 0;
  font-weight: 700;
  text-align: right;
}
</style>
