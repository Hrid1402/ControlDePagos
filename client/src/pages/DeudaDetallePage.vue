<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import DeudaDetalleSuperficie from '@/components/deudas/DeudaDetalleSuperficie.vue'
import { hoyEnLima } from '@/components/deudas/modelo'
import type { AccionDeuda, ComentarioDeuda, DetalleDeuda } from '@/components/deudas/detalle'
import EditarDeuda from '@/components/deudas/EditarDeuda.vue'
import {
  anularDeuda,
  cancelarInicio,
  comentarDeuda,
  editarDeuda,
  subirRecibo,
  iniciarPago,
  listarComentarios,
  obtenerDeuda,
} from '@/api/deudas'
import {
  aprobarComprobante,
  obtenerComprobante,
  rechazarComprobante,
  subirComprobante,
} from '@/api/comprobantes'
import { useSesionStore } from '@/stores/sesion'
import type { ErrorApi } from '@/types/api'

// H17 con datos reales (TASK-55): GET /deudas/:id y sus comentarios. Las acciones solo aparecen si
// el backend las manda y cada una se vuelve a validar al ejecutarse (CA07).
const route = useRoute()
const router = useRouter()
const toast = useToast()
const sesion = useSesionStore()

const detalle = ref<DetalleDeuda | null>(null)
const comentarios = ref<ComentarioDeuda[]>([])
const estadoPantalla = ref<'lista' | 'cargando' | 'error' | 'no_encontrada'>('cargando')
const ocupado = ref<AccionDeuda | null>(null)
const enviando = ref(false)
const errorComentario = ref<string | null>(null)
const superficie = ref<InstanceType<typeof DeudaDetalleSuperficie> | null>(null)
const selectorArchivo = ref<HTMLInputElement | null>(null)
const id = computed(() => String(route.params.id))

let solicitud: AbortController | null = null
let espera: ReturnType<typeof setTimeout> | undefined

async function cargar(silencioso = false) {
  solicitud?.abort()
  const actual = new AbortController()
  solicitud = actual
  if (!silencioso) estadoPantalla.value = 'cargando'
  try {
    const [deuda, conversacion] = await Promise.all([
      obtenerDeuda(id.value, actual.signal),
      listarComentarios(id.value),
    ])
    detalle.value = deuda
    comentarios.value = conversacion
    estadoPantalla.value = 'lista'
    vigilarValidacion()
  } catch (fallo) {
    if (actual.signal.aborted) return
    if (silencioso) return
    estadoPantalla.value = (fallo as ErrorApi).status === 404 ? 'no_encontrada' : 'error'
  }
}

/** Mientras un comprobante se valida, se vuelve a consultar cada pocos segundos (CA03 de H24). */
function vigilarValidacion() {
  clearTimeout(espera)
  if (detalle.value?.comprobantes.some((c) => c.estado === 'procesando'))
    espera = setTimeout(() => void cargar(true), 4000)
}

watch(id, () => void cargar(), { immediate: true })
onBeforeUnmount(() => {
  solicitud?.abort()
  clearTimeout(espera)
})

function avisarError(fallo: unknown) {
  toast.add({
    severity: 'error',
    summary: 'No se pudo completar',
    detail: (fallo as ErrorApi).detail,
    life: 6000,
  })
}

async function ejecutar(accion: AccionDeuda, trabajo: () => Promise<void>) {
  ocupado.value = accion
  try {
    await trabajo()
    await cargar(true)
  } catch (fallo) {
    avisarError(fallo)
    await cargar(true)
  } finally {
    ocupado.value = null
  }
}

// Cancelar el intento de otra persona exige el motivo (TASK-75).
const cancelando = ref(false)
const motivo = ref('')
const esDueno = computed(() => detalle.value?.en_proceso?.usuario_id === sesion.usuario?.id)

function accion(nombre: AccionDeuda) {
  if (nombre === 'iniciar_pago')
    return ejecutar(nombre, async () => {
      const inicio = await iniciarPago(id.value)
      toast.add(
        inicio.resultado === 'requiere_aprobacion'
          ? {
              severity: 'info',
              summary: 'Se pidió aprobación',
              detail: 'Supera tu límite: el gerente debe aprobar el pago antes de hacerlo.',
              life: 6000,
            }
          : {
              severity: 'success',
              summary: 'Pago iniciado',
              detail: 'Cuando pagues, adjunta aquí el comprobante.',
              life: 5000,
            },
      )
    })
  if (nombre === 'adjuntar_comprobante') return selectorArchivo.value?.click()
  if (nombre === 'cancelar_inicio') {
    motivo.value = ''
    cancelando.value = true
  }
  if (nombre === 'editar') editando.value = true
  if (nombre === 'anular') {
    motivoAnular.value = ''
    anulando.value = true
  }
}

// Editar (H11 CA10): solo viaja lo que cambió; el recibo se sube aparte.
const editando = ref(false)
async function guardarEdicion(valores: Record<string, unknown>) {
  const actual = detalle.value!
  const cambios: Record<string, string> = {}
  for (const campo of ['monto', 'fecha_vencimiento', 'numero_recibo'] as const) {
    const valor = String(valores[campo] ?? '').trim()
    if (valor && valor !== (actual[campo] ?? '')) cambios[campo] = valor
  }
  if (Object.keys(cambios).length) detalle.value = await editarDeuda(id.value, cambios)
  if (valores.recibo instanceof File) detalle.value = await subirRecibo(id.value, valores.recibo)
  editando.value = false
}

// Anular (H11 CA11): pide confirmación y deja la deuda como historial.
const anulando = ref(false)
const motivoAnular = ref('')
async function confirmarAnulacion() {
  anulando.value = false
  await ejecutar('anular', async () => {
    detalle.value = await anularDeuda(id.value, motivoAnular.value.trim() || null)
    toast.add({ severity: 'success', summary: 'Deuda anulada', life: 4000 })
  })
}

async function confirmarCancelacion() {
  const texto = motivo.value.trim()
  if (!esDueno.value && !texto) return
  cancelando.value = false
  await ejecutar('cancelar_inicio', async () => {
    await cancelarInicio(id.value, texto || null)
    toast.add({ severity: 'success', summary: 'Pago cancelado', life: 4000 })
  })
}

async function adjuntar(evento: Event) {
  const entrada = evento.target as HTMLInputElement
  const archivo = entrada.files?.[0]
  entrada.value = ''
  if (!archivo) return
  await ejecutar('adjuntar_comprobante', async () => {
    await subirComprobante(id.value, archivo)
    toast.add({
      severity: 'success',
      summary: 'Comprobante adjuntado',
      detail: 'Se está validando; el resultado aparece aquí en unos segundos.',
      life: 5000,
    })
  })
}

async function abrirComprobante(comprobanteId: string) {
  try {
    const comprobante = await obtenerComprobante(comprobanteId)
    if (comprobante.archivo_enlace) window.open(comprobante.archivo_enlace, '_blank', 'noopener')
  } catch (fallo) {
    avisarError(fallo)
  }
}

// El gerente valida o rechaza el voucher que subió la asistente (H24 CA07, TASK-109).
const validando = ref<string | null>(null)
const rechazando = ref<string | null>(null)
const motivoRechazo = ref('')

async function decidir(comprobanteId: string, trabajo: () => Promise<unknown>, aviso: string) {
  validando.value = comprobanteId
  try {
    await trabajo()
    toast.add({ severity: 'success', summary: aviso, life: 4000 })
  } catch (fallo) {
    avisarError(fallo)
  } finally {
    validando.value = null
    await cargar(true)
  }
}

function validarComprobante(comprobanteId: string) {
  return decidir(comprobanteId, () => aprobarComprobante(comprobanteId), 'Pago validado')
}

function pedirRechazo(comprobanteId: string) {
  motivoRechazo.value = ''
  rechazando.value = comprobanteId
}

async function confirmarRechazo() {
  const comprobanteId = rechazando.value
  const texto = motivoRechazo.value.trim()
  if (!comprobanteId || !texto) return
  rechazando.value = null
  await decidir(
    comprobanteId,
    () => rechazarComprobante(comprobanteId, texto),
    'Voucher rechazado: la asistente recibe el motivo',
  )
}

async function comentar(texto: string) {
  enviando.value = true
  errorComentario.value = null
  try {
    comentarios.value.push(await comentarDeuda(id.value, texto))
    superficie.value?.limpiarComentario()
  } catch (fallo) {
    errorComentario.value = (fallo as ErrorApi).detail
  } finally {
    enviando.value = false
  }
}

/** Vuelve a la lista con sus filtros si se llegó desde ella (CA09 de H36). */
function volver() {
  if (window.history.state?.back) return router.back()
  return router.push({ name: sesion.rol === 'gerente' ? 'gerente-deudas' : 'asistente-inicio' })
}
</script>

<template>
  <DeudaDetalleSuperficie
    ref="superficie"
    :detalle="detalle"
    :comentarios="comentarios"
    :estado-pantalla="estadoPantalla"
    :hoy="hoyEnLima()"
    :ocupado="ocupado"
    :enviando-comentario="enviando"
    :error-comentario="errorComentario"
    @volver="volver"
    @accion="accion"
    @comentar="comentar"
    @abrir-comprobante="abrirComprobante"
    :puede-validar="sesion.rol === 'gerente'"
    :validando="validando"
    @validar-comprobante="validarComprobante"
    @rechazar-comprobante="pedirRechazo"
    @reintentar="cargar()"
  />
  <input
    ref="selectorArchivo"
    type="file"
    accept="application/pdf,image/jpeg,image/png"
    class="oculto"
    aria-label="Elegir el comprobante"
    @change="adjuntar"
  />
  <EditarDeuda
    v-if="editando && detalle"
    :deuda="detalle"
    :guardar="guardarEdicion"
    @cerrar="editando = false"
  />
  <Dialog
    v-model:visible="anulando"
    modal
    header="¿Anular esta deuda?"
    :style="{ width: 'min(92vw, 460px)' }"
  >
    <p class="explica">
      Deja de cobrarse y queda solo como historial: no se borra ni se puede pagar después.
    </p>
    <label for="motivo-anular" class="etiqueta">Motivo (opcional)</label>
    <textarea id="motivo-anular" v-model="motivoAnular" rows="3" maxlength="300"></textarea>
    <template #footer>
      <Button label="Volver" text @click="anulando = false" />
      <Button label="Anular deuda" severity="danger" @click="confirmarAnulacion" />
    </template>
  </Dialog>
  <Dialog
    :visible="!!rechazando"
    modal
    header="Rechazar el voucher"
    :style="{ width: 'min(92vw, 460px)' }"
    @update:visible="!$event && (rechazando = null)"
  >
    <p class="explica">
      La asistente recibe el motivo y sube otro voucher. Este queda como historial.
    </p>
    <label for="motivo-rechazo" class="etiqueta">Motivo</label>
    <textarea id="motivo-rechazo" v-model="motivoRechazo" rows="3" maxlength="500"></textarea>
    <template #footer>
      <Button label="Volver" text @click="rechazando = null" />
      <Button
        label="Rechazar voucher"
        severity="danger"
        :disabled="!motivoRechazo.trim()"
        @click="confirmarRechazo"
      />
    </template>
  </Dialog>
  <Dialog
    v-model:visible="cancelando"
    modal
    header="Cancelar el pago en curso"
    :style="{ width: 'min(92vw, 460px)' }"
  >
    <p class="explica">
      La deuda vuelve a quedar por pagar y se libera lo reservado. Úsalo solo si el pago no se hizo.
    </p>
    <label for="motivo-cancelar" class="etiqueta"> Motivo {{ esDueno ? '(opcional)' : '' }} </label>
    <textarea id="motivo-cancelar" v-model="motivo" rows="3" maxlength="300"></textarea>
    <p v-if="!esDueno" class="ayuda">Lo inició otra persona: indica por qué lo cancelas.</p>
    <template #footer>
      <Button label="Volver" text @click="cancelando = false" />
      <Button
        label="Cancelar el pago"
        severity="danger"
        :disabled="!esDueno && !motivo.trim()"
        @click="confirmarCancelacion"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.oculto {
  display: none;
}
.explica {
  margin: 0 0 16px;
  line-height: 1.5;
}
.etiqueta {
  display: block;
  margin-bottom: 6px;
  font-weight: 700;
}
textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #7b8798;
  border-radius: var(--radio-control);
  font: inherit;
}
.ayuda {
  margin: 6px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
</style>
