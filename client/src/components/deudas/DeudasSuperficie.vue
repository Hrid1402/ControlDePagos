<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Button from 'primevue/button'
import { tintaSobre } from '@/components/categorias/modelo'
import EtiquetaDeuda from './EtiquetaDeuda.vue'
import { fechaCorta, plazo } from './estados'
import { importe, MONEDAS, nombrePeriodo, type Moneda } from './modelo'
import {
  hayFiltros,
  nombreDeuda,
  ORDENES,
  TAMANO_PAGINA,
  VISTAS,
  type CategoriaDeuda,
  type FiltrosDeudas,
  type ItemDeuda,
  type Totales,
} from './listado'

// H36: lista de deudas con búsqueda, filtros, orden, totales por moneda y paginación de 20. Quien
// la usa trae los datos y decide qué pasa al filtrar, paginar o abrir una deuda (TASK-46).
const props = withDefaults(
  defineProps<{
    items?: ItemDeuda[]
    total?: number
    totales?: Totales | null
    categorias?: CategoriaDeuda[]
    filtros: FiltrosDeudas
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    /** Hoy en Lima (AAAA-MM-DD), para «vence en 3 días». */
    hoy: string
  }>(),
  { items: () => [], total: 0, totales: null, categorias: () => [], estadoPantalla: 'lista' },
)
const emit = defineEmits<{
  filtrar: [cambios: Partial<FiltrosDeudas>]
  limpiar: []
  abrir: [id: string]
  registrar: []
  registrarServicio: []
  reintentar: []
}>()

// La búsqueda espera a que se deje de escribir para no pedir una página por cada tecla.
const texto = ref(props.filtros.q)
let espera: ReturnType<typeof setTimeout> | undefined
watch(
  () => props.filtros.q,
  (nuevo) => (texto.value = nuevo),
)
function escribir(valor: string) {
  texto.value = valor
  clearTimeout(espera)
  espera = setTimeout(() => emit('filtrar', { q: valor.trim(), page: 1 }), 300)
}
onBeforeUnmount(() => clearTimeout(espera))

const filtrando = computed(() => hayFiltros(props.filtros))
// Sin ninguna deuda (CA11) los filtros no sirven: solo se muestra cómo empezar.
const conHerramientas = computed(
  () => props.items.length > 0 || filtrando.value || props.estadoPantalla !== 'lista',
)
const paginas = computed(() => Math.max(1, Math.ceil(props.total / TAMANO_PAGINA)))
const desde = computed(() => (props.filtros.page - 1) * TAMANO_PAGINA + 1)
const hasta = computed(() => Math.min(props.total, props.filtros.page * TAMANO_PAGINA))

/** Una tarjeta por moneda con deudas en el filtro: soles y dólares nunca se suman. */
const resumen = computed(() =>
  MONEDAS.flatMap((m) => {
    const t = props.totales?.[m.valor]
    if (!t || t.cantidad === 0) return []
    const monto = Number(t.monto)
    return [
      {
        moneda: m.valor,
        etiqueta: m.etiqueta,
        ...t,
        avance: monto > 0 ? Math.min(100, (Number(t.pagado) / monto) * 100) : 0,
      },
    ]
  }),
)

const cerrada = (d: ItemDeuda) => d.estado === 'pagada' || d.estado === 'anulada'
const plazoDe = (d: ItemDeuda) => plazo(d.fecha_vencimiento, props.hoy, cerrada(d))
const categoriaElegida = computed(() =>
  props.categorias.find((c) => c.id === props.filtros.categoria),
)
const vistaElegida = computed(() => VISTAS.find((v) => v.valor === props.filtros.vista))
const monto = (valor: string, moneda: Moneda) => importe(valor, moneda)
</script>

<template>
  <section class="deudas" aria-labelledby="deudas-titulo">
    <header class="encabezado">
      <div>
        <h1 id="deudas-titulo">Deudas</h1>
        <p>Lo que falta pagar, lo que está en camino y lo que ya se pagó.</p>
      </div>
      <Button label="Registrar deuda" icon="pi pi-plus" @click="emit('registrar')" />
    </header>

    <div v-if="resumen.length && estadoPantalla === 'lista'" class="resumen">
      <article
        v-for="r in resumen"
        :key="r.moneda"
        class="total"
        :aria-label="`Totales en ${r.etiqueta.toLowerCase()}`"
      >
        <p class="total-titulo">Saldo por pagar · {{ r.etiqueta }}</p>
        <p class="total-cifra">{{ monto(r.saldo, r.moneda) }}</p>
        <div
          class="avance"
          role="meter"
          :aria-valuenow="Math.round(r.avance)"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="`Pagado ${Math.round(r.avance)} %`"
        >
          <span :style="{ width: `${r.avance}%` }"></span>
        </div>
        <dl class="total-detalle">
          <div>
            <dt>Total</dt>
            <dd>{{ monto(r.monto, r.moneda) }}</dd>
          </div>
          <div>
            <dt>Pagado</dt>
            <dd>{{ monto(r.pagado, r.moneda) }}</dd>
          </div>
          <div>
            <dt>Deudas</dt>
            <dd>{{ r.cantidad }}</dd>
          </div>
        </dl>
        <p v-if="r.sin_monto" class="total-nota">
          <i class="pi pi-hourglass" aria-hidden="true"></i>
          {{ r.sin_monto === 1 ? '1 espera su recibo' : `${r.sin_monto} esperan su recibo` }}
          <template v-if="Number(r.proyectado) > 0">
            · estimado {{ monto(r.proyectado, r.moneda) }}, aparte del total
          </template>
          <template v-if="r.sin_estimacion"> · {{ r.sin_estimacion }} sin estimación</template>
        </p>
      </article>
    </div>

    <div v-if="conHerramientas" class="herramientas">
      <label class="buscador">
        <i class="pi pi-search" aria-hidden="true"></i>
        <span class="lector">Buscar deudas</span>
        <input
          type="search"
          :value="texto"
          placeholder="Busca por empresa, alias, código o recibo"
          @input="escribir(($event.target as HTMLInputElement).value)"
        />
      </label>
      <label class="selector">
        <span>Categoría</span>
        <select
          :value="filtros.categoria"
          @change="
            emit('filtrar', { categoria: ($event.target as HTMLSelectElement).value, page: 1 })
          "
        >
          <option value="">Todas</option>
          <option v-for="c in categorias" :key="c.id" :value="c.id">{{ c.nombre }}</option>
        </select>
      </label>
      <label class="selector">
        <span>Mes</span>
        <input
          type="month"
          :value="filtros.mes"
          @change="emit('filtrar', { mes: ($event.target as HTMLInputElement).value, page: 1 })"
        />
      </label>
      <label class="selector">
        <span>Ordenar</span>
        <select
          :value="filtros.orden"
          @change="
            emit('filtrar', {
              orden: ($event.target as HTMLSelectElement).value as FiltrosDeudas['orden'],
              page: 1,
            })
          "
        >
          <option v-for="o in ORDENES" :key="o.valor" :value="o.valor">{{ o.etiqueta }}</option>
        </select>
      </label>
    </div>

    <div v-if="conHerramientas" class="vistas" role="group" aria-label="Mostrar deudas">
      <button
        v-for="v in VISTAS"
        :key="v.valor"
        type="button"
        :aria-pressed="filtros.vista === v.valor"
        @click="emit('filtrar', { vista: v.valor, page: 1 })"
      >
        {{ v.etiqueta }}
      </button>
    </div>

    <div v-if="estadoPantalla === 'cargando'" aria-busy="true" class="cargando">
      <p class="lector" role="status">Cargando deudas…</p>
      <div v-for="n in 6" :key="n" class="marcador"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar las deudas.</h2>
      <p>Revisa tu conexión e inténtalo otra vez. Tus filtros se conservan.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="emit('reintentar')" />
    </div>

    <section v-else-if="!items.length" class="vacio" aria-live="polite">
      <template v-if="filtrando">
        <span class="vacio-icono" aria-hidden="true"><i class="pi pi-filter-slash"></i></span>
        <h2>Ninguna deuda coincide</h2>
        <p>
          No hay resultados
          <template v-if="vistaElegida && filtros.vista !== 'activas'">
            en «{{ vistaElegida.etiqueta }}»</template
          ><template v-if="categoriaElegida"> de {{ categoriaElegida.nombre }}</template
          ><template v-if="filtros.mes"> para {{ nombrePeriodo(filtros.mes) }}</template
          ><template v-if="filtros.q"> que digan «{{ filtros.q }}»</template>.
        </p>
        <Button label="Limpiar filtros" icon="pi pi-times" outlined @click="emit('limpiar')" />
      </template>
      <template v-else>
        <span class="vacio-icono" aria-hidden="true"><i class="pi pi-receipt"></i></span>
        <h2>Todavía no hay deudas</h2>
        <p>
          Las deudas salen de tus servicios: registra la luz, el agua o la tarjeta una vez, y cada
          mes su deuda aparece aquí.
        </p>
        <div class="vacio-acciones">
          <Button
            label="Registrar un servicio"
            icon="pi pi-plus"
            @click="emit('registrarServicio')"
          />
          <Button label="Registrar deuda" text @click="emit('registrar')" />
        </div>
      </template>
    </section>

    <template v-else>
      <div class="conteo">
        <p role="status">
          {{ total === 1 ? '1 deuda' : `${total} deudas` }}
          <template v-if="paginas > 1"> · ves de la {{ desde }} a la {{ hasta }}</template>
        </p>
        <button v-if="filtrando" type="button" class="limpiar" @click="emit('limpiar')">
          <i class="pi pi-times" aria-hidden="true"></i> Limpiar filtros
        </button>
      </div>

      <table class="tabla">
        <caption class="lector">
          Deudas
        </caption>
        <thead>
          <tr>
            <th scope="col">Deuda</th>
            <th scope="col">Categoría</th>
            <th scope="col">Periodo</th>
            <th scope="col">Vence</th>
            <th scope="col" class="derecha">Monto</th>
            <th scope="col">Estado</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="d in items"
            :key="d.id"
            :class="{ anulada: d.estado === 'anulada' }"
            @click="emit('abrir', d.id)"
          >
            <td class="c-deuda">
              <div class="deuda-celda">
                <span
                  class="icono"
                  aria-hidden="true"
                  :style="{ background: d.categoria.color, color: tintaSobre(d.categoria.color) }"
                >
                  <i class="pi" :class="d.categoria.icono"></i>
                </span>
                <span class="nombre-bloque">
                  <button type="button" class="nombre" @click.stop="emit('abrir', d.id)">
                    {{ nombreDeuda(d) }}
                  </button>
                  <span class="sub">
                    <template v-if="d.alias">{{ d.empresa }} · </template>
                    <span class="codigo">{{ d.codigo_suministro }}</span>
                  </span>
                </span>
              </div>
            </td>
            <td class="c-categoria">
              <span
                class="punto"
                :style="{ background: d.categoria.color }"
                aria-hidden="true"
              ></span>
              {{ d.categoria.nombre }}
            </td>
            <td class="c-periodo">{{ nombrePeriodo(d.periodo) }}</td>
            <td class="c-vence">
              <span class="fecha">{{ fechaCorta(d.fecha_vencimiento, hoy) }}</span>
              <span v-if="plazoDe(d).texto" class="plazo" :class="`plazo-${plazoDe(d).tono}`">{{
                plazoDe(d).texto
              }}</span>
            </td>
            <td class="c-monto derecha">
              <template v-if="d.monto !== null">
                <span class="cifra">{{ monto(d.monto, d.moneda) }}</span>
                <span
                  v-if="Number(d.pagado) > 0 && d.saldo !== null && d.estado !== 'pagada'"
                  class="sub"
                >
                  Saldo {{ monto(d.saldo, d.moneda) }}
                </span>
              </template>
              <template v-else>
                <span class="por-confirmar">Por confirmar</span>
                <span v-if="d.monto_proyectado" class="sub">
                  ≈ {{ monto(d.monto_proyectado, d.moneda) }} estimado
                </span>
              </template>
            </td>
            <td class="c-estado"><EtiquetaDeuda :estado="d.estado" /></td>
          </tr>
        </tbody>
      </table>

      <nav v-if="paginas > 1" class="paginacion" aria-label="Páginas de deudas">
        <Button
          label="Anterior"
          icon="pi pi-arrow-left"
          text
          :disabled="filtros.page <= 1"
          @click="emit('filtrar', { page: filtros.page - 1 })"
        />
        <span>Página {{ filtros.page }} de {{ paginas }}</span>
        <Button
          label="Siguiente"
          icon="pi pi-arrow-right"
          icon-pos="right"
          text
          :disabled="filtros.page >= paginas"
          @click="emit('filtrar', { page: filtros.page + 1 })"
        />
      </nav>
    </template>
  </section>
</template>

<style scoped>
.deudas {
  max-width: 1120px;
}
.encabezado {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px 32px;
  margin-bottom: clamp(20px, 3vw, 28px);
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.encabezado p {
  margin: 10px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
.encabezado :deep(.p-button) {
  min-height: 44px;
}

/* Totales: una tarjeta por moneda, en papel claro sobre la hoja. */
.resumen {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.total {
  padding: 18px 20px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 4px 22px 4px 4px;
  background: var(--deconsta-paper-claro);
}
.total p,
.total dl {
  margin: 0;
}
.total-titulo {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-weight: 600;
}
.total-cifra {
  margin-top: 4px !important;
  font-family: Literata, Georgia, serif;
  font-size: clamp(1.75rem, 1.4rem + 1vw, 2.25rem);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}
.avance {
  height: 6px;
  margin: 12px 0;
  overflow: hidden;
  border-radius: 999px;
  background: var(--deconsta-realce);
}
.avance span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--deconsta-primary);
}
.total-detalle {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 24px;
  font-size: var(--texto-sm);
}
.total-detalle div {
  display: flex;
  gap: 6px;
}
.total-detalle dt {
  color: var(--deconsta-muted);
}
.total-detalle dd {
  margin: 0;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.total-nota {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 12px !important;
  padding-top: 10px;
  border-top: 1px dashed var(--deconsta-linea);
  color: #34506e;
  font-size: var(--texto-sm);
}

/* Herramientas */
.herramientas {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 12px;
}
.buscador {
  position: relative;
  flex: 1 1 300px;
}
.buscador .pi {
  position: absolute;
  top: 50%;
  left: 14px;
  color: var(--deconsta-muted);
  transform: translateY(-50%);
}
.buscador input,
.selector select,
.selector input {
  width: 100%;
  min-height: 46px;
  border: 1px solid #7b8798;
  border-radius: var(--radio-control);
  background: #fff;
  color: var(--deconsta-ink);
  font: inherit;
}
.buscador input {
  padding: 0 14px 0 40px;
}
.selector {
  display: grid;
  flex: 0 1 190px;
  gap: 4px;
}
.selector span {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 700;
  letter-spacing: 0.02em;
}
.selector select,
.selector input {
  padding: 0 12px;
}
.buscador input:focus-visible,
.selector select:focus-visible,
.selector input:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 1px;
}
.vistas {
  display: flex;
  gap: 8px;
  margin: 16px 0 20px;
  padding-bottom: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}
.vistas button {
  flex-shrink: 0;
  min-height: 38px;
  padding: 0 16px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 999px;
  background: var(--deconsta-paper-claro);
  color: var(--deconsta-ink);
  font: inherit;
  font-size: var(--texto-sm);
  font-weight: 600;
  cursor: pointer;
}
.vistas button[aria-pressed='true'] {
  border-color: var(--deconsta-ink);
  background: var(--deconsta-ink);
  color: var(--deconsta-paper);
}
button:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
.conteo {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.conteo p {
  margin: 0;
}
.limpiar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 4px;
  border: 0;
  background: none;
  color: var(--deconsta-primary);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

/* Tabla */
.tabla {
  width: 100%;
  border-collapse: collapse;
  border-top: 1px solid var(--deconsta-ink);
}
.tabla th {
  padding: 10px 12px;
  border-bottom: 1px solid var(--deconsta-linea);
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-align: left;
  text-transform: uppercase;
}
.tabla td {
  padding: 14px 12px;
  border-bottom: 1px solid var(--deconsta-linea);
  vertical-align: middle;
}
.tabla tbody tr {
  cursor: pointer;
  transition: background-color 120ms ease;
}
.tabla tbody tr:hover {
  background: var(--deconsta-paper-claro);
}
.derecha {
  text-align: right !important;
}
.deuda-celda {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 220px;
}
.icono {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 4px 14px 4px 4px;
}
.nombre-bloque {
  display: grid;
  min-width: 0;
}
.nombre {
  justify-self: start;
  padding: 0;
  border: 0;
  background: none;
  color: var(--deconsta-ink);
  font: inherit;
  font-weight: 700;
  text-align: left;
  overflow-wrap: anywhere;
  cursor: pointer;
}
tr:hover .nombre {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.sub {
  display: block;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.codigo {
  font-family: ui-monospace, 'SFMono-Regular', Menlo, monospace;
  letter-spacing: 0.02em;
}
.c-categoria {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  white-space: nowrap;
}
.punto {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 6px;
  border-radius: 50%;
}
.c-periodo {
  font-size: var(--texto-sm);
  white-space: nowrap;
}
.c-periodo::first-letter {
  text-transform: uppercase;
}
.c-vence {
  white-space: nowrap;
}
.fecha {
  display: block;
  font-weight: 600;
}
.plazo {
  display: block;
  font-size: var(--texto-xs);
  font-weight: 700;
}
.plazo-peligro {
  color: var(--deconsta-error);
}
.plazo-aviso {
  color: var(--deconsta-aviso);
}
.plazo-neutro {
  color: var(--deconsta-muted);
  font-weight: 500;
}
.cifra {
  display: block;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.por-confirmar {
  display: block;
  color: #34506e;
  font-weight: 700;
}
tr.anulada .nombre,
tr.anulada .cifra {
  color: var(--deconsta-muted);
  text-decoration: line-through;
}
.paginacion {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding-top: 16px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}

/* Estados de la pantalla */
.vacio {
  max-width: 56ch;
  margin: 8px auto 0;
  padding: clamp(28px, 5vw, 56px) 0;
  text-align: center;
}
.vacio-icono {
  display: inline-grid;
  place-items: center;
  width: 56px;
  height: 56px;
  margin-bottom: 14px;
  border-radius: 4px 20px 4px 4px;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-size: 1.4rem;
}
.vacio h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.vacio p {
  margin: 8px 0 20px;
  color: var(--deconsta-muted);
  line-height: 1.6;
}
.vacio-acciones {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
.fallo {
  max-width: 52ch;
  padding: 24px 28px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo h2 {
  margin: 0;
  font-size: var(--texto-lg);
}
.fallo p {
  margin: 8px 0 20px;
}
.marcador {
  height: 64px;
  margin-bottom: 8px;
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
@keyframes brillo {
  to {
    background-position: -200% 0;
  }
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* Tablet: la categoría y el periodo pasan debajo del nombre. */
@media (max-width: 960px) {
  .tabla th:nth-child(2),
  .c-categoria {
    display: none;
  }
}

/* Celular: cada deuda es una tarjeta de dos columnas. */
@media (max-width: 720px) {
  .encabezado :deep(.p-button) {
    width: 100%;
  }
  .selector {
    flex: 1 1 calc(50% - 6px);
  }
  .tabla thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .tabla,
  .tabla tbody {
    display: block;
  }
  .tabla tbody tr {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      'deuda monto'
      'estado vence';
    gap: 8px 12px;
    padding: 14px 2px;
    border-bottom: 1px solid var(--deconsta-linea);
  }
  .tabla td {
    padding: 0;
    border: 0;
  }
  .c-deuda {
    grid-area: deuda;
    min-width: 0;
  }
  .deuda-celda {
    min-width: 0;
  }
  .c-monto {
    grid-area: monto;
  }
  .c-estado {
    grid-area: estado;
    padding-left: 52px !important;
  }
  .c-vence {
    grid-area: vence;
    text-align: right;
  }
  .c-vence .fecha {
    display: none;
  }
  .c-periodo {
    display: none;
  }
}
</style>
