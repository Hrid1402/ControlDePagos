<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import DeudaDetalleSuperficie from '@/components/deudas/DeudaDetalleSuperficie.vue'
import { COLORES, ICONOS } from '@/components/categorias/modelo'
import { LUGARES_PAGO } from '@/components/servicios/modelo'
import { ESTADOS, type EstadoDeuda } from '@/components/deudas/estados'
import { hoyEnLima, type Moneda } from '@/components/deudas/modelo'
import type {
  AccionDeuda,
  CambioMonto,
  ComentarioDeuda,
  ComprobanteDeLaDeuda,
  DetalleDeuda,
  EventoDeuda,
} from '@/components/deudas/detalle'

// Solo en desarrollo (/revision/detalle-deuda). Quien revisa arma la deuda con sus valores, le
// agrega comprobantes, cambios de monto y comentarios: la página no trae datos propios. Las
// acciones imitan las reglas de GET /deudas/:id; la API se conecta en TASK-55.
const f = reactive({
  empresa: '',
  alias: '',
  codigo: '',
  categoria: '',
  color: COLORES[0]!.valor,
  estado: 'pendiente' as EstadoDeuda,
  monto: '',
  proyectado: '',
  moneda: 'PEN' as Moneda,
  vencimiento: hoyEnLima(),
  lugar: '',
  recibo: false,
  rol: 'asistente' as 'gerente' | 'asistente',
  urgente: false,
})
const hoy = ref(hoyEnLima())
const estadoPantalla = ref<'lista' | 'cargando' | 'error' | 'no_encontrada'>('lista')
const comprobantes = ref<ComprobanteDeLaDeuda[]>([])
const historial = ref<CambioMonto[]>([])
const eventos = ref<EventoDeuda[]>([])
const comentarios = ref<ComentarioDeuda[]>([])
const ultimaAccion = ref('')
const superficie = ref<InstanceType<typeof DeudaDetalleSuperficie> | null>(null)

const ahora = () => new Date().toISOString()
const autor = () => ({ nombre: f.rol === 'gerente' ? 'Gerente' : 'Asistente', rol: f.rol })

function agregarComprobante(estado: ComprobanteDeLaDeuda['estado']) {
  const observaciones: Partial<Record<ComprobanteDeLaDeuda['estado'], string>> = {
    rechazado: 'No se pudo leer el comprobante. Toma otra foto con buena luz y reemplázalo.',
    en_revision: 'El comprobante es por más de lo que cubre: lo revisa el gerente.',
  }
  comprobantes.value.unshift({
    id: crypto.randomUUID(),
    estado,
    motivo_codigo: estado === 'rechazado' ? 'ilegible' : null,
    observacion: observaciones[estado] ?? null,
    monto: f.monto || null,
    monto_aplicado: f.monto || '0.00',
    moneda: f.moneda,
    subido_por: autor().nombre,
    creado_en: ahora(),
    reemplaza_a_id: null,
  })
  eventos.value.unshift({ tipo: 'comprobante_subido', fecha: ahora(), actor: autor(), detalle: {} })
  if (estado !== 'procesando')
    eventos.value.unshift({
      tipo: `comprobante_${estado}`,
      fecha: ahora(),
      actor: null,
      detalle: {},
    })
}

function cambiarMonto() {
  const anterior = f.monto || '0.00'
  const nuevo = (Number(anterior) + 10).toFixed(2)
  historial.value.unshift({
    monto_anterior: anterior,
    monto_nuevo: nuevo,
    origen: 'manual',
    usuario: 'Gerente',
    creado_en: ahora(),
  })
  eventos.value.unshift({
    tipo: 'deuda_monto_cambiado',
    fecha: ahora(),
    actor: { nombre: 'Gerente', rol: 'gerente' },
    detalle: { monto_anterior: anterior, monto_nuevo: nuevo },
  })
  f.monto = nuevo
}

const pagado = computed(() =>
  comprobantes.value
    .filter((c) => c.estado === 'validado')
    .reduce((suma, c) => suma + Number(c.monto_aplicado), 0),
)

const acciones = computed<AccionDeuda[]>(() => {
  if (f.estado === 'anulada') return []
  const lista: AccionDeuda[] = []
  if (['pendiente', 'pagada_parcial'].includes(f.estado) && f.monto) lista.push('iniciar_pago')
  if (f.estado === 'en_proceso') lista.push('cancelar_inicio')
  const adjuntar =
    ['en_proceso', 'por_validar'].includes(f.estado) ||
    (f.rol === 'gerente' && ['pendiente', 'pagada_parcial'].includes(f.estado))
  if (adjuntar && f.monto) lista.push('adjuntar_comprobante')
  if (f.rol === 'gerente' && f.estado !== 'pagada') lista.push('editar', 'anular')
  lista.push('comentar')
  return lista
})

const detalle = computed<DetalleDeuda | null>(() => {
  if (!f.empresa.trim()) return null
  const monto = f.monto || null
  return {
    id: 'revision',
    servicio: {
      id: 's',
      empresa: f.empresa.trim(),
      alias: f.alias.trim() || null,
      codigo_suministro: f.codigo || '00000000',
      titular: null,
      lugar_pago: f.lugar || null,
      notas: null,
    },
    categoria: {
      id: 'c',
      nombre: f.categoria || 'Servicios',
      color: f.color,
      icono: ICONOS[0]!.valor,
      tipo: 'servicio_variable',
    },
    periodo: f.vencimiento.slice(0, 7),
    estado: f.estado,
    origen: 'manual',
    moneda: f.moneda,
    monto,
    pagado: pagado.value.toFixed(2),
    saldo: monto ? (Number(monto) - pagado.value).toFixed(2) : null,
    monto_proyectado: monto ? null : f.proyectado || null,
    vencida: f.vencimiento < hoy.value,
    fecha_emision: null,
    fecha_vencimiento: f.vencimiento,
    fecha_estimada: null,
    fecha_corte: null,
    pago_minimo: null,
    pago_total: null,
    numero_recibo: f.recibo ? 'F001-000123' : null,
    recibo_enlace: f.recibo ? '/brand/deconsta/social/og-image.png' : null,
    cuota_numero: null,
    cuotas_total: null,
    en_proceso:
      f.estado === 'en_proceso'
        ? { usuario_id: 'u', rol: f.rol, nombre: autor().nombre, desde: ahora() }
        : null,
    orden_urgente: f.urgente ? { id: 'o', estado: 'enviada', plazo: null } : null,
    creado_en: ahora(),
    comprobantes: comprobantes.value,
    historial_montos: historial.value,
    linea_tiempo: [
      ...eventos.value,
      { tipo: 'deuda_creada', fecha: ahora(), actor: autor(), detalle: {} },
    ],
    acciones: acciones.value,
  }
})

function comentar(texto: string) {
  comentarios.value.push({
    id: crypto.randomUUID(),
    texto,
    autor: autor().nombre,
    rol: f.rol,
    propio: true,
    creado_en: ahora(),
  })
  superficie.value?.limpiarComentario()
}
</script>

<template>
  <div class="revision">
    <header class="borde">
      <img
        src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
        alt="Deconsta"
        width="132"
        height="26"
      />
      <span>Revisión de diseño</span>
    </header>
    <main class="hoja">
      <p v-if="!detalle && estadoPantalla === 'lista'" class="guia">
        Escribe una empresa en «Controles de revisión» para ver el detalle.
      </p>
      <DeudaDetalleSuperficie
        v-else
        ref="superficie"
        :detalle="detalle"
        :comentarios="comentarios"
        :estado-pantalla="estadoPantalla"
        :hoy="hoy"
        @volver="ultimaAccion = 'Volvería a la lista con sus filtros.'"
        @accion="ultimaAccion = `Acción: ${$event}`"
        @abrir-comprobante="ultimaAccion = `Abriría el comprobante ${$event}`"
        @comentar="comentar"
        @reintentar="estadoPantalla = 'lista'"
      />
      <p v-if="ultimaAccion" class="nota" role="status">{{ ultimaAccion }}</p>
    </main>
    <details class="controles" open>
      <summary>Controles de revisión</summary>
      <p>Esta ruta solo existe en desarrollo.</p>
      <div class="grupo">
        <label>Empresa <input v-model="f.empresa" /></label>
        <label>Alias <input v-model="f.alias" /></label>
        <label>Código <input v-model="f.codigo" /></label>
        <label>Categoría <input v-model="f.categoria" /></label>
        <label
          >Color
          <select v-model="f.color">
            <option v-for="c in COLORES" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
          </select></label
        >
        <label
          >Estado
          <select v-model="f.estado">
            <option v-for="(e, clave) in ESTADOS" :key="clave" :value="clave">
              {{ e.etiqueta }}
            </option>
          </select></label
        >
        <label>Monto (vacío: sin recibo) <input v-model="f.monto" inputmode="decimal" /></label>
        <label>Estimado <input v-model="f.proyectado" inputmode="decimal" /></label>
        <label
          >Moneda
          <select v-model="f.moneda">
            <option value="PEN">PEN</option>
            <option value="USD">USD</option>
          </select></label
        >
        <label>Vencimiento <input v-model="f.vencimiento" type="date" /></label>
        <label>Hoy es <input v-model="hoy" type="date" /></label>
        <label
          >Lugar de pago
          <select v-model="f.lugar">
            <option value="">Sin indicar</option>
            <option v-for="l in LUGARES_PAGO" :key="l.valor" :value="l.valor">
              {{ l.etiqueta }}
            </option>
          </select></label
        >
        <label
          >Como
          <select v-model="f.rol">
            <option value="asistente">Asistente</option>
            <option value="gerente">Gerente</option>
          </select></label
        >
        <label class="casilla"><input v-model="f.recibo" type="checkbox" /> Con recibo</label>
        <label class="casilla"><input v-model="f.urgente" type="checkbox" /> Orden urgente</label>
      </div>
      <div class="grupo">
        <button type="button" @click="agregarComprobante('validado')">Comprobante validado</button>
        <button type="button" @click="agregarComprobante('en_revision')">En revisión</button>
        <button type="button" @click="agregarComprobante('rechazado')">Rechazado</button>
        <button type="button" @click="agregarComprobante('procesando')">Validando</button>
        <button type="button" @click="cambiarMonto">Cambiar monto (+10)</button>
        <label
          >Pantalla
          <select v-model="estadoPantalla">
            <option value="lista">Detalle</option>
            <option value="cargando">Cargando</option>
            <option value="error">Error</option>
            <option value="no_encontrada">No encontrada</option>
          </select></label
        >
      </div>
    </details>
  </div>
</template>

<style scoped>
.revision {
  min-height: 100svh;
  padding: 0 var(--margen-mesa) var(--margen-mesa);
  background: var(--deconsta-primary);
}
.borde {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 72px;
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-sm);
}
.borde img {
  display: block;
  width: 132px;
  height: auto;
}
.hoja {
  padding: clamp(24px, 4vw, 56px);
  border-radius: var(--radio-hoja);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
}
.guia,
.nota {
  margin: 0;
  color: var(--deconsta-muted);
}
.nota {
  margin-top: 16px;
  font-size: var(--texto-sm);
}
.controles {
  margin-top: 16px;
  padding: 14px 18px;
  border-radius: var(--radio-control);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
  font-size: var(--texto-sm);
}
.controles summary {
  font-weight: 700;
  cursor: pointer;
}
.grupo {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 10px 16px;
  margin-top: 12px;
}
.grupo label {
  display: grid;
  gap: 4px;
}
.grupo label.casilla {
  display: flex;
  align-items: center;
  gap: 6px;
}
.grupo input:not([type='checkbox']),
.grupo select,
.grupo button {
  min-height: 34px;
  padding: 0 8px;
}
</style>
