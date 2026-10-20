<script setup lang="ts">
import { ref } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { nombreServicio, type ServicioDetalle } from './modelo'
import type { ErrorApi } from '@/types/api'

// H10 CA08: la baja frena las deudas nuevas y conserva las pendientes. Solo el gerente.
const props = defineProps<{
  servicio: ServicioDetalle
  confirmar: () => Promise<unknown>
}>()
const emit = defineEmits<{ cerrar: [] }>()

const enviando = ref(false)
const error = ref('')

async function dar() {
  enviando.value = true
  error.value = ''
  try {
    await props.confirmar()
  } catch (fallo) {
    error.value = (fallo as ErrorApi).detail || 'No pudimos darlo de baja. Inténtalo otra vez.'
  } finally {
    enviando.value = false
  }
}
</script>

<template>
  <Dialog
    visible
    modal
    :header="`Dar de baja ${nombreServicio(servicio)}`"
    :draggable="false"
    :style="{ width: 'min(500px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <ul class="efectos">
      <li>
        <i class="pi pi-ban" aria-hidden="true"></i>
        Dejará de generar deudas nuevas: sus recurrencias se desactivan.
      </li>
      <li v-if="servicio.deudas_pendientes">
        <i class="pi pi-clock" aria-hidden="true"></i>
        {{
          servicio.deudas_pendientes === 1
            ? 'La deuda pendiente se conserva y se puede pagar.'
            : `Las ${servicio.deudas_pendientes} deudas pendientes se conservan y se pueden pagar.`
        }}
      </li>
      <li>
        <i class="pi pi-replay" aria-hidden="true"></i>
        Puedes reactivarlo cuando lo necesites.
      </li>
    </ul>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="botones">
      <Button label="Cancelar" text @click="emit('cerrar')" />
      <Button label="Dar de baja" severity="danger" :loading="enviando" @click="dar" />
    </div>
  </Dialog>
</template>

<style scoped>
.efectos {
  display: grid;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.efectos li {
  display: flex;
  gap: 12px;
  line-height: 1.5;
}
.efectos .pi {
  margin-top: 4px;
  color: var(--deconsta-muted);
}
.error {
  margin: 16px 0 0;
  color: var(--deconsta-error);
  font-weight: 600;
}
.botones {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 22px;
}
</style>
