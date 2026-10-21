<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import DeudasSuperficie from '@/components/deudas/DeudasSuperficie.vue'
import { COLORES, ICONOS } from '@/components/categorias/modelo'
import { ESTADOS, type EstadoDeuda } from '@/components/deudas/estados'
import { hoyEnLima, sumarMeses, type Moneda } from '@/components/deudas/modelo'
import {
  FILTROS_INICIALES,
  TAMANO_PAGINA,
  VISTAS,
  type CategoriaDeuda,
  type FiltrosDeudas,
  type ItemDeuda,
  type Totales,
} from '@/components/deudas/listado'

// Solo en desarrollo (/revision/deudas). Quien revisa agrega deudas con sus valores y la página
// filtra, ordena, pagina y totaliza en memoria como GET /deudas: no trae datos propios. La API se
// conecta en TASK-46.
const deudas = ref<ItemDeuda[]>([])
const categorias = ref<CategoriaDeuda[]>([])
const filtros = ref<FiltrosDeudas>({ ...FILTROS_INICIALES })
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('lista')
const hoy = ref(hoyEnLima())
const abierta = ref<string | null>(null)

const nueva = reactive({
  empresa: '',
  alias: '',
  categoria: '',
  color: COLORES[0]!.valor,
  monto: '',
  pagado: '',
  proyectado: '',
  moneda: 'PEN' as Moneda,
  vencimiento: hoyEnLima(),
  estado: 'pendiente' as EstadoDeuda,
  meses: 1,
})

function categoriaDe(nombre: string): CategoriaDeuda {
  const existente = categorias.value.find((c) => c.nombre === nombre)
  if (existente) return existente
  const categoria = {
    id: crypto.randomUUID(),
    nombre,
    color: nueva.color,
    icono: ICONOS[categorias.value.length % ICONOS.length]!.valor,
    tipo: 'servicio_variable',
  }
  categorias.value.push(categoria)
  return categoria
}

function agregar() {
  if (!nueva.empresa.trim()) return
  const categoria = categoriaDe(nueva.categoria.trim() || 'Servicios')
  const servicio = crypto.randomUUID()
  const codigo = String(Math.floor(Math.random() * 1e8)).padStart(8, '0')
  for (let i = 0; i < Math.max(1, nueva.meses); i++) {
    const vencimiento = sumarMeses(nueva.vencimiento, -i)
    const monto = nueva.monto.trim() || null
    const pagado = monto && nueva.pagado ? nueva.pagado : '0.00'
    deudas.value.push({
      id: crypto.randomUUID(),
      servicio_id: servicio,
      empresa: nueva.empresa.trim(),
      alias: nueva.alias.trim() || null,
      codigo_suministro: codigo,
      categoria,
      periodo: vencimiento.slice(0, 7),
      monto,
      moneda: nueva.moneda,
      pagado,
      saldo: monto ? (Number(monto) - Number(pagado)).toFixed(2) : null,
      monto_proyectado: monto ? null : nueva.proyectado || null,
      fecha_vencimiento: vencimiento,
      vencida: false,
      estado: nueva.estado,
      numero_recibo: null,
    })
  }
  nueva.empresa = ''
  nueva.alias = ''
}

const CERRADAS = ['pagada', 'anulada']
const conVencida = computed(() =>
  deudas.value.map((d) => ({
    ...d,
    vencida: d.fecha_vencimiento < hoy.value && !CERRADAS.includes(d.estado),
  })),
)

const filtradas = computed(() => {
  const f = filtros.value
  const vista = VISTAS.find((v) => v.valor === f.vista)!
  const texto = f.q.toLowerCase()
  return conVencida.value
    .filter((d) =>
      vista.estados.length ? vista.estados.includes(d.estado) : d.estado !== 'anulada',
    )
    .filter((d) => !vista.vencida || d.vencida)
    .filter((d) => !f.categoria || d.categoria.id === f.categoria)
    .filter((d) => !f.mes || d.periodo === f.mes)
    .filter(
      (d) =>
        !texto ||
        [d.empresa, d.alias, d.codigo_suministro].some((v) => v?.toLowerCase().includes(texto)),
    )
    .sort((a, b) => {
      const signo = f.orden.startsWith('-') ? -1 : 1
      if (f.orden.endsWith('monto')) return signo * (Number(a.monto ?? 0) - Number(b.monto ?? 0))
      if (f.orden === 'estado') return a.estado.localeCompare(b.estado)
      return signo * a.fecha_vencimiento.localeCompare(b.fecha_vencimiento)
    })
})

const pagina = computed(() =>
  filtradas.value.slice(
    (filtros.value.page - 1) * TAMANO_PAGINA,
    filtros.value.page * TAMANO_PAGINA,
  ),
)

const totales = computed<Totales>(() => {
  const vacio = () => ({
    cantidad: 0,
    monto: 0,
    pagado: 0,
    saldo: 0,
    sin_monto: 0,
    proyectado: 0,
    sin_estimacion: 0,
  })
  const suma = { PEN: vacio(), USD: vacio() }
  for (const d of filtradas.value) {
    const t = suma[d.moneda]
    t.cantidad++
    if (d.monto === null) {
      t.sin_monto++
      if (d.monto_proyectado) t.proyectado += Number(d.monto_proyectado)
      else t.sin_estimacion++
    } else {
      t.monto += Number(d.monto)
      t.pagado += Number(d.pagado)
      t.saldo += Number(d.saldo)
    }
  }
  const texto = (t: ReturnType<typeof vacio>) => ({
    ...t,
    monto: t.monto.toFixed(2),
    pagado: t.pagado.toFixed(2),
    saldo: t.saldo.toFixed(2),
    proyectado: t.proyectado.toFixed(2),
  })
  return { PEN: texto(suma.PEN), USD: texto(suma.USD) }
})

const aviso = ref('')
function avisar(texto: string) {
  aviso.value = texto
  setTimeout(() => (aviso.value = ''), 2500)
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
      <DeudasSuperficie
        :items="pagina"
        :total="filtradas.length"
        :totales="totales"
        :categorias="categorias"
        :filtros="filtros"
        :estado-pantalla="estadoPantalla"
        :hoy="hoy"
        @filtrar="filtros = { ...filtros, ...$event }"
        @limpiar="filtros = { ...FILTROS_INICIALES, orden: filtros.orden }"
        @abrir="abierta = $event"
        @registrar="avisar('Abre el formulario de deuda (TASK-41).')"
        @registrar-servicio="avisar('Lleva a Servicios para registrar el primero.')"
        @reintentar="estadoPantalla = 'lista'"
      />
      <p v-if="abierta" class="nota" role="status">Abriría el detalle de la deuda {{ abierta }}.</p>
      <p v-if="aviso" class="nota" role="status">{{ aviso }}</p>
    </main>
    <details class="controles" open>
      <summary>Controles de revisión</summary>
      <p>
        Esta ruta solo existe en desarrollo. Agrega deudas para ver la tabla, los totales y la
        paginación; con «Meses» se crean varias del mismo servicio hacia atrás.
      </p>
      <form class="grupo" @submit.prevent="agregar">
        <label>Empresa <input v-model="nueva.empresa" required /></label>
        <label>Alias <input v-model="nueva.alias" /></label>
        <label>Categoría <input v-model="nueva.categoria" placeholder="Luz" /></label>
        <label
          >Color
          <select v-model="nueva.color">
            <option v-for="c in COLORES" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
          </select></label
        >
        <label>Monto (vacío: sin recibo) <input v-model="nueva.monto" inputmode="decimal" /></label>
        <label>Pagado <input v-model="nueva.pagado" inputmode="decimal" /></label>
        <label>Estimado <input v-model="nueva.proyectado" inputmode="decimal" /></label>
        <label
          >Moneda
          <select v-model="nueva.moneda">
            <option value="PEN">PEN</option>
            <option value="USD">USD</option>
          </select></label
        >
        <label>Vencimiento <input v-model="nueva.vencimiento" type="date" /></label>
        <label
          >Estado
          <select v-model="nueva.estado">
            <option v-for="(e, clave) in ESTADOS" :key="clave" :value="clave">
              {{ e.etiqueta }}
            </option>
          </select></label
        >
        <label>Meses <input v-model.number="nueva.meses" type="number" min="1" max="36" /></label>
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
        <label>Hoy es <input v-model="hoy" type="date" /></label>
        <button type="button" @click="deudas = []">Vaciar</button>
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
.grupo select {
  min-height: 34px;
  padding: 0 8px;
}
</style>
