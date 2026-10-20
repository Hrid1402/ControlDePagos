<script setup lang="ts">
import { computed } from 'vue'
import Dialog from 'primevue/dialog'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import CampoMuestras from './CampoMuestras.vue'
import CampoTipo from './CampoTipo.vue'
import { crearCategoria, editarCategoria, type DatosCategoria } from '@/api/categorias'
import {
  COLORES,
  ICONOS,
  esquemaCategoria,
  etiquetaTipo,
  tintaSobre,
  type Categoria,
} from './modelo'

// H09 CA02 a CA04: crear (gerente o asistente) y editar (solo gerente) una categoría.
const props = defineProps<{ categoria?: Categoria | null }>()
const emit = defineEmits<{ guardada: [categoria: Categoria]; cerrar: [] }>()

const editando = computed(() => !!props.categoria)
const iniciales = computed(() => ({
  nombre: props.categoria?.nombre ?? '',
  tipo: props.categoria?.tipo ?? '',
  color: props.categoria?.color ?? COLORES[7]!.valor,
  icono: props.categoria?.icono ?? 'pi-tag',
}))
// CA03: sus deudas ya se registraron con los campos de este tipo.
const tipoBloqueado = computed(() =>
  props.categoria && props.categoria.cantidad_deudas > 0
    ? 'El tipo no se puede cambiar porque ya tiene deudas registradas con él.'
    : null,
)

async function guardar(valores: Record<string, unknown>) {
  const datos = valores as unknown as DatosCategoria
  const guardada = props.categoria
    ? await editarCategoria(props.categoria.id, datos)
    : await crearCategoria(datos)
  emit('guardada', guardada)
}
</script>

<template>
  <Dialog
    visible
    modal
    :header="editando ? `Editar ${categoria!.nombre}` : 'Nueva categoría'"
    :draggable="false"
    :style="{ width: 'min(640px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <FormularioBase
      :esquema="esquemaCategoria"
      :valores-iniciales="iniciales"
      :guardar="guardar"
      :texto-boton="editando ? 'Guardar cambios' : 'Crear categoría'"
      :mensaje-exito="editando ? 'La categoría se actualizó.' : 'La categoría se creó.'"
    >
      <template #default="{ valores }">
        <div class="cabecera">
          <span
            class="vista"
            aria-hidden="true"
            :style="{ background: String(valores.color), color: tintaSobre(String(valores.color)) }"
          >
            <i class="pi" :class="String(valores.icono)"></i>
          </span>
          <CampoTexto nombre="nombre" etiqueta="Nombre" autocomplete="off" />
        </div>
        <p class="nota">
          Así se verá:
          <strong>{{ String(valores.nombre || 'Sin nombre').trim() }}</strong>
          <template v-if="valores.tipo"
            >, {{ etiquetaTipo(String(valores.tipo)).toLowerCase() }}</template
          >.
        </p>
        <CampoTipo :bloqueado="tipoBloqueado" />
        <div class="apariencia">
          <CampoMuestras nombre="color" etiqueta="Color" variante="color" :opciones="COLORES" />
          <CampoMuestras
            nombre="icono"
            etiqueta="Ícono"
            variante="icono"
            :opciones="ICONOS"
            :fondo="String(valores.color)"
            :tinta="tintaSobre(String(valores.color))"
          />
        </div>
      </template>
    </FormularioBase>
  </Dialog>
</template>

<style scoped>
.cabecera {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: end;
  gap: 16px;
}
.vista {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  border-radius: 5px 20px 5px 5px;
  font-size: 1.375rem;
  transition: background 0.2s ease;
}
.nota {
  margin: -6px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.apariencia {
  display: grid;
  gap: 18px;
}
</style>
