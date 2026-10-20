<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import ServiciosSuperficie from '@/components/servicios/ServiciosSuperficie.vue'
import FormularioServicio from '@/components/servicios/FormularioServicio.vue'
import DialogoBajaServicio from '@/components/servicios/DialogoBajaServicio.vue'
import { COLORES, ICONOS } from '@/components/categorias/modelo'
import {
  GRUPOS_EMPRESA,
  type CategoriaServicio,
  type DatosServicio,
  type Empresa,
  type FiltroEstado,
  type ServicioDetalle,
} from '@/components/servicios/modelo'

// Solo en desarrollo (/revision/servicios). Quien revisa agrega categorías y empresas y registra
// servicios con el formulario real: la página no trae datos propios. La API se conecta en TASK-34.
const categorias = ref<CategoriaServicio[]>([])
const empresas = ref<Empresa[]>([])
const servicios = ref<ServicioDetalle[]>([])
const busqueda = ref('')
const categoria = ref('')
const estado = ref<FiltroEstado>('activo')
const estadoPantalla = ref<'lista' | 'cargando' | 'error'>('lista')
const gerente = ref(true)
const deudasAlEditar = ref(0)
const formulario = ref<{ servicio: ServicioDetalle | null } | null>(null)
const bajando = ref<ServicioDetalle | null>(null)

const nuevaCategoria = reactive({ nombre: '', color: COLORES[0]!.valor, icono: ICONOS[0]!.valor })
const nuevaEmpresa = reactive({
  nombre: '',
  tipo_servicio: 'luz' as Empresa['tipo_servicio'],
  patron: '',
})

const visibles = computed(() => {
  const texto = busqueda.value.toLowerCase()
  return servicios.value.filter(
    (s) =>
      (estado.value === 'todos' || s.estado === estado.value) &&
      (!categoria.value || s.categoria.id === categoria.value) &&
      (!texto ||
        [s.alias, s.empresa, s.codigo_suministro, s.titular].some((v) =>
          v?.toLowerCase().includes(texto),
        )),
  )
})

function agregarCategoria() {
  if (!nuevaCategoria.nombre.trim()) return
  categorias.value.push({
    id: crypto.randomUUID(),
    nombre: nuevaCategoria.nombre.trim(),
    tipo: 'servicio_variable',
    color: nuevaCategoria.color,
    icono: nuevaCategoria.icono,
  })
  nuevaCategoria.nombre = ''
}

function agregarEmpresa() {
  if (!nuevaEmpresa.nombre.trim()) return
  empresas.value.push({
    id: crypto.randomUUID(),
    nombre: nuevaEmpresa.nombre.trim(),
    tipo_servicio: nuevaEmpresa.tipo_servicio,
    patron_codigo: nuevaEmpresa.patron.trim() || null,
  })
  nuevaEmpresa.nombre = ''
  nuevaEmpresa.patron = ''
}

async function guardar(datos: DatosServicio) {
  const cat = categorias.value.find((c) => c.id === datos.categoria_id)!
  const empresa = empresas.value.find((e) => e.id === datos.empresa_id)
  const editado = formulario.value?.servicio
  const fila: ServicioDetalle = {
    id: editado?.id ?? crypto.randomUUID(),
    categoria: cat,
    empresa_id: datos.empresa_id,
    empresa: empresa?.nombre ?? datos.empresa_nombre ?? '',
    empresa_manual: !empresa,
    codigo_suministro: datos.codigo_suministro,
    titular: datos.titular,
    alias: datos.alias,
    lugar_pago: datos.lugar_pago,
    notas: datos.notas,
    estado: 'activo',
    deudas_pendientes: editado?.deudas_pendientes ?? 0,
  }
  servicios.value = editado
    ? servicios.value.map((s) => (s.id === editado.id ? fila : s))
    : [fila, ...servicios.value]
  formulario.value = null
}

function editar(id: string) {
  const s = servicios.value.find((x) => x.id === id)
  if (s) formulario.value = { servicio: { ...s, deudas_pendientes: deudasAlEditar.value } }
}

function cambiarEstado(id: string, nuevo: 'activo' | 'baja') {
  servicios.value = servicios.value.map((s) => (s.id === id ? { ...s, estado: nuevo } : s))
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
      <ServiciosSuperficie
        :servicios="visibles"
        :total="visibles.length"
        :categorias="categorias"
        :busqueda="busqueda"
        :categoria="categoria"
        :estado="estado"
        :estado-pantalla="estadoPantalla"
        :puede-dar-de-baja="gerente"
        @buscar="busqueda = $event"
        @filtrar-categoria="categoria = $event"
        @filtrar-estado="estado = $event"
        @crear="formulario = { servicio: null }"
        @editar="editar"
        @baja="bajando = servicios.find((s) => s.id === $event) ?? null"
        @reactivar="cambiarEstado($event, 'activo')"
        @reintentar="estadoPantalla = 'lista'"
      />
    </main>
    <details class="controles">
      <summary>Controles de revisión</summary>
      <p>Esta ruta solo existe en desarrollo. Los datos reales se conectan en TASK-34.</p>
      <form class="grupo" @submit.prevent="agregarCategoria">
        <label>Categoría <input v-model="nuevaCategoria.nombre" /></label>
        <label
          >Color
          <select v-model="nuevaCategoria.color">
            <option v-for="c in COLORES" :key="c.valor" :value="c.valor">{{ c.etiqueta }}</option>
          </select></label
        >
        <label
          >Ícono
          <select v-model="nuevaCategoria.icono">
            <option v-for="i in ICONOS" :key="i.valor" :value="i.valor">{{ i.etiqueta }}</option>
          </select></label
        >
        <button type="submit">Agregar categoría</button>
      </form>
      <form class="grupo" @submit.prevent="agregarEmpresa">
        <label>Empresa <input v-model="nuevaEmpresa.nombre" /></label>
        <label
          >Servicio
          <select v-model="nuevaEmpresa.tipo_servicio">
            <option v-for="(etiqueta, valor) in GRUPOS_EMPRESA" :key="valor" :value="valor">
              {{ etiqueta }}
            </option>
          </select></label
        >
        <label>Patrón del código <input v-model="nuevaEmpresa.patron" placeholder="\d{8}" /></label>
        <button type="submit">Agregar empresa</button>
      </form>
      <div class="grupo">
        <label
          >Lista
          <select v-model="estadoPantalla">
            <option value="lista">Lista</option>
            <option value="cargando">Cargando</option>
            <option value="error">Error</option>
          </select></label
        >
        <label
          >Deudas pendientes al editar
          <input v-model.number="deudasAlEditar" type="number" min="0" />
        </label>
        <label class="casilla"><input v-model="gerente" type="checkbox" /> Como gerente</label>
      </div>
    </details>
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
      :confirmar="
        async () => {
          cambiarEstado(bajando!.id, 'baja')
          bajando = null
        }
      "
      @cerrar="bajando = null"
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
.grupo select {
  min-height: 34px;
  padding: 0 8px;
}
</style>
