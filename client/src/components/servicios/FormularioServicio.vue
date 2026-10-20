<script setup lang="ts">
import { computed } from 'vue'
import Dialog from 'primevue/dialog'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import CampoSeleccion from '@/components/formularios/CampoSeleccion.vue'
import CampoEmpresa from './CampoEmpresa.vue'
import CampoLugarPago from './CampoLugarPago.vue'
import CampoNotas from './CampoNotas.vue'
import {
  OTRA_EMPRESA,
  aDatos,
  esquemaServicio,
  valoresDe,
  type CategoriaServicio,
  type DatosServicio,
  type Empresa,
  type ServicioDetalle,
} from './modelo'

// H10 CA01 a CA07 y CA09: registrar o editar un servicio. Gerente y asistente pueden hacerlo en
// cualquier categoría. Guardar lo resuelve quien lo usa (la API en TASK-34).
const props = defineProps<{
  servicio?: ServicioDetalle | null
  empresas: Empresa[]
  categorias: CategoriaServicio[]
  guardar: (datos: DatosServicio) => Promise<unknown>
}>()
const emit = defineEmits<{ cerrar: [] }>()

const editando = computed(() => !!props.servicio)
const esquema = computed(() => esquemaServicio(props.empresas))
const iniciales = computed(() => valoresDe(props.servicio ?? null))
const opcionesCategoria = computed(() =>
  props.categorias.map((c) => ({ valor: c.id, etiqueta: c.nombre })),
)

/** CA07: el código cambia y el servicio tiene deudas sin pagar con el anterior. */
function avisoCodigo(codigo: unknown): string | null {
  const s = props.servicio
  if (!s || !s.deudas_pendientes) return null
  if (String(codigo ?? '').trim() === s.codigo_suministro) return null
  const n = s.deudas_pendientes
  return `${n === 1 ? 'Tiene 1 deuda pendiente' : `Tiene ${n} deudas pendientes`} con el código ${s.codigo_suministro}. Al guardar seguirán ahí con sus montos: revisa que correspondan al código nuevo.`
}
const patronDe = (empresa: unknown) =>
  props.empresas.find((e) => e.id === empresa)?.patron_codigo ?? null

async function guardar(valores: Record<string, unknown>) {
  await props.guardar(aDatos(valores))
}
</script>

<template>
  <Dialog
    visible
    modal
    :header="editando ? 'Editar servicio' : 'Nuevo servicio'"
    :draggable="false"
    :style="{ width: 'min(720px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <FormularioBase
      :esquema="esquema"
      :valores-iniciales="iniciales"
      :guardar="guardar"
      :texto-boton="editando ? 'Guardar cambios' : 'Registrar servicio'"
      :mensaje-exito="editando ? 'El servicio se actualizó.' : 'El servicio se registró.'"
      :limpiar-al-guardar="!editando"
    >
      <template #default="{ valores }">
        <section class="bloque" aria-labelledby="servicio-empresa">
          <h3 id="servicio-empresa">Empresa y código</h3>
          <div class="par">
            <CampoEmpresa :empresas="empresas" />
            <CampoTexto
              v-if="valores.empresa === OTRA_EMPRESA"
              nombre="empresa_nombre"
              etiqueta="Nombre de la empresa"
              autocomplete="off"
            />
          </div>
          <CampoTexto
            nombre="codigo_suministro"
            etiqueta="Código de suministro"
            autocomplete="off"
            spellcheck="false"
            :ayuda="
              patronDe(valores.empresa)
                ? 'Está en tu recibo. Lo validamos con el formato de la empresa.'
                : 'Está en tu recibo, como «N.º de suministro» o «Código de cliente».'
            "
          />
          <p v-if="avisoCodigo(valores.codigo_suministro)" class="aviso" role="note">
            {{ avisoCodigo(valores.codigo_suministro) }}
          </p>
        </section>

        <section class="bloque" aria-labelledby="servicio-reconocer">
          <h3 id="servicio-reconocer">Cómo lo reconoces</h3>
          <div class="par">
            <CampoTexto
              nombre="alias"
              etiqueta="Alias (opcional)"
              placeholder="Luz oficina"
              autocomplete="off"
            />
            <CampoTexto nombre="titular" etiqueta="Titular (opcional)" autocomplete="off" />
          </div>
          <CampoSeleccion
            nombre="categoria_id"
            etiqueta="Categoría"
            vacia="Elige una categoría"
            :opciones="opcionesCategoria"
          />
        </section>

        <section class="bloque" aria-labelledby="servicio-pago">
          <h3 id="servicio-pago" class="lector">Pago</h3>
          <CampoLugarPago />
          <CampoNotas />
        </section>
      </template>
    </FormularioBase>
  </Dialog>
</template>

<style scoped>
.bloque {
  display: grid;
  gap: 16px;
}
.bloque + .bloque {
  margin-top: 4px;
  padding-top: 20px;
  border-top: 1px solid var(--deconsta-linea);
}
h3 {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-weight: 700;
}
.par {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}
.aviso {
  margin: 0;
  padding: 12px 14px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  font-size: var(--texto-sm);
  line-height: 1.5;
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@media (max-width: 560px) {
  .par {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
