<script setup lang="ts">
import { reactive, ref } from 'vue'
import FormularioDeuda from '@/components/deudas/FormularioDeuda.vue'
import { COLORES, ICONOS, TIPOS, type TipoCategoria } from '@/components/categorias/modelo'
import {
  hoyEnLima,
  importe,
  periodoDe,
  type DatosDeuda,
  type DeudaExistente,
} from '@/components/deudas/modelo'
import type { Servicio } from '@/components/servicios/modelo'

// Solo en desarrollo (/revision/deuda). Quien revisa crea servicios de cada tipo de categoría y
// registra deudas con el formulario real: la página no trae datos propios. La API se conecta en
// TASK-41; aquí las deudas viven en memoria para ver el duplicado (CA03).
const servicios = ref<Servicio[]>([])
const registradas = ref<(DatosDeuda & { id: string })[]>([])
const abierto = ref(false)
const duplicada = ref<DeudaExistente | null>(null)
const hoy = ref(hoyEnLima())
const nuevo = reactive({
  nombre: '',
  tipo: 'servicio_variable' as TipoCategoria,
  color: COLORES[0]!.valor,
})

function agregarServicio() {
  if (!nuevo.nombre.trim()) return
  const tipo = TIPOS.find((t) => t.valor === nuevo.tipo)!
  servicios.value.push({
    id: crypto.randomUUID(),
    categoria: {
      id: nuevo.tipo,
      nombre: tipo.etiqueta,
      tipo: nuevo.tipo,
      color: nuevo.color,
      icono: ICONOS[0]!.valor,
    },
    empresa_id: null,
    empresa: nuevo.nombre.trim(),
    empresa_manual: true,
    codigo_suministro: String(servicios.value.length + 1).padStart(6, '0'),
    titular: null,
    alias: null,
    lugar_pago: null,
    notas: null,
    estado: 'activo',
  })
  nuevo.nombre = ''
}

async function guardar(datos: DatosDeuda) {
  duplicada.value = null
  const periodo =
    datos.periodo ?? (datos.fecha_vencimiento ? periodoDe(datos.fecha_vencimiento) : '')
  const existente = registradas.value.find(
    (d) =>
      d.tipo !== 'prestamo' &&
      d.servicio_id === datos.servicio_id &&
      (d.periodo ?? periodoDe(d.fecha_vencimiento!)) === periodo,
  )
  if (datos.tipo !== 'prestamo' && existente) {
    duplicada.value = {
      id: existente.id,
      periodo,
      estado: 'pendiente',
      monto: existente.monto,
      moneda: existente.moneda,
      fecha_vencimiento: existente.fecha_vencimiento!,
    }
    throw {
      status: 409,
      code: 'DUPLICADO',
      detail: 'Ya existe una deuda de este servicio para ese periodo.',
      field: 'periodo',
    }
  }
  registradas.value.unshift({ ...datos, id: crypto.randomUUID() })
  abierto.value = false
}

const nombreDe = (id: string) => servicios.value.find((s) => s.id === id)?.empresa ?? ''
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
      <header class="encabezado">
        <div>
          <h1>Formulario de deuda</h1>
          <p>
            Cada tipo de categoría pide lo suyo. Crea un servicio de cada tipo y regístrale deudas.
          </p>
        </div>
        <button
          type="button"
          class="primario"
          :disabled="!servicios.length"
          @click="abierto = true"
        >
          Nueva deuda
        </button>
      </header>
      <h2>Lo que se envió</h2>
      <p v-if="!registradas.length" class="vacio">Todavía no registraste deudas.</p>
      <ul v-else class="enviadas">
        <li v-for="d in registradas" :key="d.id">
          <strong>{{ nombreDe(d.servicio_id) }}</strong>
          <span v-if="d.tipo === 'prestamo'">
            Préstamo de {{ importe(d.monto_total!, d.moneda) }} en {{ d.cuotas_total }} cuotas
          </span>
          <span v-else>
            {{ importe(d.monto!, d.moneda) }} · vence {{ d.fecha_vencimiento }}
            <template v-if="d.pago_minimo">
              · mínimo {{ importe(d.pago_minimo, d.moneda) }}</template
            >
            <template v-if="d.repetir"> · se repite</template>
            <template v-if="d.recibo"> · {{ d.recibo.name }}</template>
          </span>
        </li>
      </ul>
    </main>
    <details class="controles" open>
      <summary>Controles de revisión</summary>
      <p>Esta ruta solo existe en desarrollo. Los datos reales se conectan en TASK-41.</p>
      <form class="grupo" @submit.prevent="agregarServicio">
        <label>Servicio <input v-model="nuevo.nombre" placeholder="Visa BCP" /></label>
        <label
          >Tipo de categoría
          <select v-model="nuevo.tipo">
            <option v-for="t in TIPOS" :key="t.valor" :value="t.valor">{{ t.etiqueta }}</option>
          </select></label
        >
        <label
          >Color
          <select v-model="nuevo.color">
            <option v-for="c in COLORES" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
          </select></label
        >
        <button type="submit">Agregar servicio</button>
      </form>
      <div class="grupo">
        <label>Hoy es <input v-model="hoy" type="date" /></label>
      </div>
    </details>
    <FormularioDeuda
      v-if="abierto"
      :servicios="servicios"
      :guardar="guardar"
      :duplicada="duplicada"
      :hoy="hoy"
      @cerrar="((abierto = false), (duplicada = null))"
      @ver-duplicada="((abierto = false), (duplicada = null))"
    />
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
.encabezado {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px 32px;
  margin-bottom: 32px;
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
}
.encabezado p,
.vacio {
  margin: 10px 0 0;
  color: var(--deconsta-muted);
}
h2 {
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--deconsta-ink);
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.primario {
  min-height: 44px;
  padding: 0 18px;
  border: 0;
  border-radius: var(--radio-control);
  background: var(--deconsta-primary);
  color: #fff;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.primario:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.enviadas {
  margin: 0;
  padding: 0;
  list-style: none;
}
.enviadas li {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--deconsta-linea);
  font-variant-numeric: tabular-nums;
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
.grupo input,
.grupo select {
  min-height: 34px;
  padding: 0 8px;
}
</style>
