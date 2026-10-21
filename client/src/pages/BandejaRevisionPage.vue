<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import BandejaSuperficie from '@/components/bandeja/BandejaSuperficie.vue'
import { COLORES, ICONOS } from '@/components/categorias/modelo'
import { LUGARES_PAGO } from '@/components/servicios/modelo'
import { hoyEnLima, sumarMeses, type Moneda } from '@/components/deudas/modelo'
import type { CategoriaDeuda } from '@/components/deudas/listado'
import type { EtiquetaPrioridad, ItemBandeja, Pestana } from '@/components/bandeja/modelo'

// Solo en desarrollo (/revision/bandeja). Quien revisa agrega deudas con su prioridad y su pestaña;
// la página ordena y cuenta como GET /bandeja sin traer datos propios. La API se conecta en TASK-50.
const NIVEL: Record<EtiquetaPrioridad, number> = {
  orden_urgente: 0,
  fijada: 1,
  vencida: 2,
  vence_hoy: 3,
  tarjeta: 4,
  proxima: 5,
}
const YO = 'yo'
const items = ref<(ItemBandeja & { pestana: Pestana; oculta: boolean })[]>([])
const categorias = ref<CategoriaDeuda[]>([])
const pestana = ref<Pestana>('por_pagar')
const categoria = ref('')
const seleccion = ref<string[]>([])
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('lista')
const hoy = ref(hoyEnLima())
const aviso = ref('')

const f = reactive({
  empresa: '',
  alias: '',
  categoria: '',
  color: COLORES[0]!.valor,
  monto: '',
  moneda: 'PEN' as Moneda,
  dias: 3,
  etiqueta: 'proxima' as EtiquetaPrioridad,
  pestana: 'por_pagar' as Pestana,
  lugar: '',
  proceso: '',
  comprobante: '',
})

function categoriaDe(nombre: string): CategoriaDeuda {
  const existente = categorias.value.find((c) => c.nombre === nombre)
  if (existente) return existente
  const nueva = {
    id: crypto.randomUUID(),
    nombre,
    color: f.color,
    icono: ICONOS[categorias.value.length % ICONOS.length]!.valor,
    tipo: f.etiqueta === 'tarjeta' ? 'tarjeta' : 'servicio_variable',
  }
  categorias.value.push(nueva)
  return nueva
}

function agregar() {
  if (!f.empresa.trim()) return
  const vencimiento = sumarMeses(hoy.value, 0)
  const fecha = new Date(`${vencimiento}T12:00:00`)
  fecha.setDate(fecha.getDate() + Number(f.dias))
  items.value.push({
    id: crypto.randomUUID(),
    empresa: f.empresa.trim(),
    alias: f.alias.trim() || null,
    codigo_suministro: String(Math.floor(Math.random() * 1e8)).padStart(8, '0'),
    lugar_pago: f.lugar || null,
    categoria: categoriaDe(f.categoria.trim() || 'Servicios'),
    monto: f.monto || null,
    moneda: f.moneda,
    saldo: f.monto || null,
    estado: f.proceso ? 'en_proceso' : 'pendiente',
    fecha_vencimiento: fecha.toISOString().slice(0, 10),
    dias_restantes: Number(f.dias),
    nivel: NIVEL[f.etiqueta],
    etiqueta: f.etiqueta,
    fijada: f.etiqueta === 'fijada',
    orden_urgente:
      f.etiqueta === 'orden_urgente' ? { id: 'o', estado: 'enviada', plazo: null } : null,
    en_proceso: f.proceso
      ? {
          usuario_id: f.proceso === YO ? YO : 'g',
          rol: f.proceso === YO ? 'asistente' : 'gerente',
          nombre: f.proceso === YO ? 'Ana Torres' : 'Carlos Ruiz',
          desde: null,
        }
      : null,
    comprobante_estado: f.comprobante || null,
    pestana: f.pestana,
    oculta: false,
  })
  f.empresa = ''
  f.alias = ''
}

const visibles = computed(() =>
  items.value
    .filter((i) => i.pestana === pestana.value && !i.oculta)
    .filter((i) => !categoria.value || i.categoria.id === categoria.value)
    .sort((a, b) => a.nivel - b.nivel || a.dias_restantes - b.dias_restantes),
)
const contadores = computed(() => {
  const contar = (p: Pestana) =>
    items.value.filter(
      (i) =>
        i.pestana === p && !i.oculta && (!categoria.value || i.categoria.id === categoria.value),
    ).length
  return {
    por_pagar: contar('por_pagar'),
    por_validar: contar('por_validar'),
    rechazadas: contar('rechazadas'),
  }
})

function fijar(id: string, valor: boolean) {
  const item = items.value.find((i) => i.id === id)
  if (!item) return
  item.fijada = valor
  if (item.etiqueta !== 'orden_urgente') {
    item.etiqueta = valor ? 'fijada' : 'proxima'
    item.nivel = valor ? 1 : 5
  }
}
function decir(texto: string) {
  aviso.value = texto
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
      <BandejaSuperficie
        :items="visibles"
        :contadores="contadores"
        :pestana="pestana"
        :categoria="categoria"
        :categorias="categorias"
        :estado-pantalla="estadoPantalla"
        :hoy="hoy"
        :seleccion="seleccion"
        :usuario-id="YO"
        nombre="Ana Torres"
        @cambiar-pestana="((pestana = $event), (seleccion = []))"
        @filtrar-categoria="categoria = $event"
        @seleccionar="seleccion = $event"
        @abrir="decir(`Abriría el detalle de ${$event}`)"
        @ventanilla="decir('Abriría el modo ventanilla (H22).')"
        @adjuntar="decir('Abriría el selector del comprobante.')"
        @fijar="fijar"
        @posponer="items.find((i) => i.id === $event)!.oculta = true"
        @agregar-ruta="decir(`Agregaría ${seleccion.length} deudas a la ruta (H23).`)"
        @reintentar="estadoPantalla = 'lista'"
      />
      <p v-if="aviso" class="nota" role="status">{{ aviso }}</p>
    </main>
    <details class="controles" open>
      <summary>Controles de revisión</summary>
      <p>Esta ruta solo existe en desarrollo.</p>
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
        <label>Monto (vacío: sin recibo) <input v-model="f.monto" inputmode="decimal" /></label>
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
          >Prioridad
          <select v-model="f.etiqueta">
            <option value="orden_urgente">Orden urgente</option>
            <option value="fijada">Fijada</option>
            <option value="vencida">Vencida</option>
            <option value="vence_hoy">Vence hoy</option>
            <option value="tarjeta">Tarjeta</option>
            <option value="proxima">Próxima</option>
          </select></label
        >
        <label
          >Pestaña
          <select v-model="f.pestana">
            <option value="por_pagar">Por pagar</option>
            <option value="por_validar">Por validar</option>
            <option value="rechazadas">Rechazadas</option>
          </select></label
        >
        <label
          >Lugar
          <select v-model="f.lugar">
            <option value="">Sin indicar</option>
            <option v-for="l in LUGARES_PAGO" :key="l.valor" :value="l.valor">
              {{ l.etiqueta }}
            </option>
          </select></label
        >
        <label
          >En proceso
          <select v-model="f.proceso">
            <option value="">No</option>
            <option :value="YO">Por mí</option>
            <option value="gerente">Por el gerente</option>
          </select></label
        >
        <label
          >Comprobante
          <select v-model="f.comprobante">
            <option value="">Sin comprobante</option>
            <option value="procesando">Validando</option>
            <option value="en_revision">En revisión</option>
            <option value="rechazado">Rechazado</option>
          </select></label
        >
        <button type="submit">Agregar</button>
      </form>
      <div class="grupo">
        <label
          >Pantalla
          <select v-model="estadoPantalla">
            <option value="lista">Lista</option>
            <option value="cargando">Cargando</option>
            <option value="error">Error</option>
          </select></label
        >
        <button type="button" @click="items = []">Vaciar</button>
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
