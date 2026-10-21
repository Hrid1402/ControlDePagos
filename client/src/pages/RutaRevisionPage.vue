<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import RutaSuperficie from '@/components/ruta/RutaSuperficie.vue'
import { COLORES, ICONOS } from '@/components/categorias/modelo'
import { LUGARES_PAGO } from '@/components/servicios/modelo'
import { hoyEnLima, type Moneda } from '@/components/deudas/modelo'
import type { CategoriaDeuda } from '@/components/deudas/listado'
import {
  pasoDe,
  type GrupoRuta,
  type ItemRuta,
  type Paso,
  type ResultadoDeuda,
  type Ruta,
} from '@/components/ruta/modelo'

// Solo en desarrollo (/revision/ruta). Quien revisa agrega deudas con su lugar y su paso; la página
// agrupa y simula el inicio en lote como GET /ruta y POST /ruta/iniciar, sin datos propios. La API
// se conecta en TASK-80.
type Lugar = (typeof LUGARES_PAGO)[number]['valor']
const ORDEN: (string | null)[] = ['agente_bcp', 'agente_kasnet', 'ventanilla_empresa', 'otro', null]

const items = ref<(ItemRuta & { lugar: Lugar | null })[]>([])
const categorias: CategoriaDeuda[] = []
const seleccion = ref<string[]>([])
const resultados = ref<ResultadoDeuda[] | null>(null)
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('lista')
const limite = ref('200')
const hoy = ref(hoyEnLima())
const aviso = ref('')

const f = reactive({
  empresa: '',
  alias: '',
  categoria: '',
  color: COLORES[0]!.valor,
  monto: '85.40',
  moneda: 'PEN' as Moneda,
  dias: 3,
  lugar: 'agente_bcp' as Lugar | '',
  paso: 'disponible' as Paso,
})

function categoriaDe(nombre: string): CategoriaDeuda {
  const existente = categorias.find((c) => c.nombre === nombre)
  if (existente) return existente
  const nueva = {
    id: crypto.randomUUID(),
    nombre,
    color: f.color,
    icono: ICONOS[categorias.length % ICONOS.length]!.valor,
    tipo: 'servicio_variable',
  }
  categorias.push(nueva)
  return nueva
}

function agregar() {
  if (!f.empresa.trim() || !Number(f.monto)) return
  const fecha = new Date(`${hoy.value}T12:00:00`)
  fecha.setDate(fecha.getDate() + Number(f.dias))
  const enRuta = !['disponible', 'espera_aprobacion'].includes(f.paso)
  items.value.push({
    id: crypto.randomUUID(),
    empresa: f.empresa.trim(),
    alias: f.alias.trim() || null,
    codigo_suministro: String(Math.floor(Math.random() * 1e8)).padStart(8, '0'),
    categoria: categoriaDe(f.categoria.trim() || 'Servicios'),
    monto: Number(f.monto).toFixed(2),
    saldo: Number(f.monto).toFixed(2),
    moneda: f.moneda,
    estado:
      f.paso === 'espera_aprobacion' ? 'esperando_aprobacion' : enRuta ? 'en_proceso' : 'pendiente',
    fecha_vencimiento: fecha.toISOString().slice(0, 10),
    en_ruta: enRuta,
    pago_realizado: ['declarada', 'validando', 'rechazado'].includes(f.paso),
    pago_realizado_en: null,
    comprobante_estado:
      f.paso === 'validando' ? 'procesando' : f.paso === 'rechazado' ? 'rechazado' : null,
    lugar: f.lugar || null,
  })
  f.empresa = ''
  f.alias = ''
}

// Como el backend: sin banca móvil, por lugar y vencimiento, con los totales por moneda.
const ruta = computed<Ruta>(() => {
  const visibles = items.value
    .filter((i) => i.lugar !== 'banca_movil')
    .sort((a, b) => a.fecha_vencimiento.localeCompare(b.fecha_vencimiento))
  const grupos: GrupoRuta[] = ORDEN.flatMap((lugar) => {
    const del = visibles.filter((i) => i.lugar === lugar)
    return del.length ? [{ lugar, items: del, totales: totalesDe(del) }] : []
  })
  return { grupos, totales: totalesDe(visibles) }
})

function totalesDe(lista: ItemRuta[]) {
  const suma = (m: Moneda) =>
    lista
      .filter((i) => i.moneda === m)
      .reduce((t, i) => t + Number(i.saldo), 0)
      .toFixed(2)
  return { PEN: suma('PEN'), USD: suma('USD') }
}

// USD y lo que supera el límite por pago piden aprobación, como iniciar_pago.
function iniciar() {
  resultados.value = seleccion.value.map((id) => {
    const item = items.value.find((i) => i.id === id)!
    if (item.moneda === 'USD' || Number(item.saldo) > Number(limite.value)) {
      item.estado = 'esperando_aprobacion'
      return {
        deuda_id: id,
        resultado: 'requiere_aprobacion',
        codigo: null,
        mensaje: null,
        repetido: false,
      }
    }
    item.estado = 'en_proceso'
    item.en_ruta = true
    return { deuda_id: id, resultado: 'iniciada', codigo: null, mensaje: null, repetido: false }
  })
  seleccion.value = []
}

function marcar(id: string) {
  const item = items.value.find((i) => i.id === id)!
  item.pago_realizado = true
  item.pago_realizado_en = new Date().toISOString()
}

function adjuntar(id: string) {
  items.value.find((i) => i.id === id)!.comprobante_estado = 'procesando'
}

const pasos = computed(() => items.value.map((i) => `${i.alias || i.empresa}: ${pasoDe(i)}`))
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
      <RutaSuperficie
        :ruta="ruta"
        :estado-pantalla="estadoPantalla"
        :hoy="hoy"
        :seleccion="seleccion"
        :resultados="resultados"
        @seleccionar="seleccion = $event"
        @iniciar="iniciar"
        @marcar="marcar"
        @adjuntar="adjuntar"
        @abrir="aviso = `Abriría el detalle de ${$event}`"
        @reintentar="estadoPantalla = 'lista'"
        @cerrar-resultados="resultados = null"
        @ir-bandeja="aviso = 'Volvería a la bandeja.'"
      />
      <p v-if="aviso" class="nota" role="status">{{ aviso }}</p>
    </main>
    <details class="controles" open>
      <summary>Controles de revisión</summary>
      <p>Esta ruta solo existe en desarrollo. Pasos: {{ pasos.join(' · ') || 'ninguno' }}</p>
      <form class="grupo" @submit.prevent="agregar">
        <label>Empresa <input v-model="f.empresa" required /></label>
        <label>Alias <input v-model="f.alias" /></label>
        <label>Categoría <input v-model="f.categoria" /></label>
        <label
          >Color
          <select v-model="f.color">
            <option v-for="c in COLORES" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
          </select></label
        >
        <label>Saldo <input v-model="f.monto" inputmode="decimal" required /></label>
        <label
          >Moneda
          <select v-model="f.moneda">
            <option value="PEN">PEN</option>
            <option value="USD">USD</option>
          </select></label
        >
        <label
          >Días para vencer <input v-model.number="f.dias" type="number" min="-60" max="60"
        /></label>
        <label
          >Lugar
          <select v-model="f.lugar">
            <option value="">Sin lugar registrado</option>
            <option v-for="l in LUGARES_PAGO" :key="l.valor" :value="l.valor">
              {{ l.etiqueta }}
            </option>
          </select></label
        >
        <label
          >Paso
          <select v-model="f.paso">
            <option value="disponible">Disponible</option>
            <option value="espera_aprobacion">Espera aprobación</option>
            <option value="por_pagar">En mi ruta</option>
            <option value="declarada">Declarada pagada</option>
            <option value="validando">Comprobante validando</option>
            <option value="rechazado">Comprobante rechazado</option>
          </select></label
        >
        <button type="submit">Agregar</button>
      </form>
      <div class="grupo">
        <label>Límite por pago (S/) <input v-model="limite" inputmode="decimal" /></label>
        <label
          >Pantalla
          <select v-model="estadoPantalla">
            <option value="lista">Lista</option>
            <option value="cargando">Cargando</option>
            <option value="error">Error</option>
          </select></label
        >
        <button type="button" @click="((items = []), (resultados = null))">Vaciar</button>
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
.nota {
  margin: 16px 0 0;
  color: var(--deconsta-muted);
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
.grupo input,
.grupo select,
.grupo button {
  min-height: 34px;
  padding: 0 8px;
}
</style>
