<script setup lang="ts">
import { computed, ref } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { eliminarCategoria } from '@/api/categorias'
import { destinosPara, etiquetaTipo, plural, type Categoria } from './modelo'
import type { ErrorApi } from '@/types/api'

// H09 CA05: sin servicios se elimina con confirmación; con servicios, primero se elige a qué
// categoría pasan. Con deudas solo sirven las del mismo tipo, y la lista ya viene filtrada.
const props = defineProps<{ categoria: Categoria; todas: Categoria[] }>()
const emit = defineEmits<{ eliminada: [movidos: number]; cerrar: [] }>()

const destino = ref('')
const enviando = ref(false)
const error = ref('')
const destinos = computed(() => destinosPara(props.categoria, props.todas))
const conServicios = computed(() => props.categoria.cantidad_servicios > 0)
const listo = computed(() => !conServicios.value || !!destino.value)

async function eliminar() {
  if (!listo.value || enviando.value) return
  enviando.value = true
  error.value = ''
  try {
    const movidos = await eliminarCategoria(props.categoria.id, destino.value || undefined)
    emit('eliminada', movidos)
  } catch (fallo) {
    error.value = (fallo as ErrorApi).detail || 'No pudimos eliminarla. Inténtalo otra vez.'
  } finally {
    enviando.value = false
  }
}
</script>

<template>
  <Dialog
    visible
    modal
    :header="`Eliminar ${categoria.nombre}`"
    :draggable="false"
    :style="{ width: 'min(500px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <template v-if="!conServicios">
      <p>No tiene servicios. Se eliminará y no podrás recuperarla.</p>
    </template>
    <template v-else-if="destinos.length">
      <p>
        Tiene {{ plural(categoria.cantidad_servicios, 'servicio', 'servicios') }}. Elige a qué
        categoría pasan antes de eliminarla.
      </p>
      <p v-if="categoria.cantidad_deudas" class="nota">
        Como ya tiene deudas, solo puedes moverlos a otra categoría de tipo
        {{ etiquetaTipo(categoria.tipo).toLowerCase() }}: sus deudas se registraron con esos campos.
      </p>
      <label class="campo">
        <span>Mover sus servicios a</span>
        <select v-model="destino">
          <option value="" disabled>Elige una categoría</option>
          <option v-for="c in destinos" :key="c.id" :value="c.id">{{ c.nombre }}</option>
        </select>
      </label>
    </template>
    <p v-else class="aviso" role="note">
      Tiene servicios con deudas y no hay otra categoría de tipo
      {{ etiquetaTipo(categoria.tipo).toLowerCase() }} a la cual moverlos. Crea una primero.
    </p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="botones">
      <Button label="Cancelar" text @click="emit('cerrar')" />
      <Button
        :label="conServicios ? 'Mover y eliminar' : 'Eliminar'"
        severity="danger"
        :disabled="!listo || (conServicios && !destinos.length)"
        :loading="enviando"
        @click="eliminar"
      />
    </div>
  </Dialog>
</template>

<style scoped>
p {
  margin: 0 0 14px;
  line-height: 1.55;
}
.nota {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.aviso {
  padding: 12px 14px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
}
.campo {
  display: grid;
  gap: 6px;
  font-weight: 600;
}
.campo select {
  min-height: 44px;
  padding: 0 10px;
  border: 1px solid var(--deconsta-linea);
  border-radius: var(--radio-control);
  background: #fff;
  font: inherit;
  font-weight: 400;
}
.error {
  margin-top: 14px;
  color: var(--deconsta-error);
  font-weight: 600;
}
.botones {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
</style>
