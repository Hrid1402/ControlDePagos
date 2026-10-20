<script setup lang="ts">
import { useId } from 'vue'
import { useField } from 'vee-validate'
import { TIPOS } from './modelo'

// CA03: cada tipo dice qué pedirá la deuda. Bloqueado, explica por qué no se puede cambiar.
const props = defineProps<{ bloqueado?: string | null }>()
const id = useId()
const { value, errorMessage } = useField<string>('tipo')
</script>

<template>
  <fieldset
    class="tipos"
    :disabled="!!props.bloqueado"
    :aria-describedby="props.bloqueado ? `${id}-bloqueo` : undefined"
  >
    <legend>Tipo</legend>
    <p v-if="props.bloqueado" :id="`${id}-bloqueo`" class="bloqueo">{{ props.bloqueado }}</p>
    <div class="opciones">
      <label v-for="tipo in TIPOS" :key="tipo.valor" :class="{ elegido: value === tipo.valor }">
        <input v-model="value" type="radio" :name="`${id}-tipo`" :value="tipo.valor" />
        <span class="texto">
          <span class="nombre">{{ tipo.etiqueta }}</span>
          <span class="pide">{{ tipo.pide }}</span>
        </span>
      </label>
    </div>
    <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
  </fieldset>
</template>

<style scoped>
.tipos {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
legend {
  margin-bottom: 8px;
  padding: 0;
  font-weight: 600;
}
.opciones {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--deconsta-linea);
  border-radius: 4px 14px 4px 4px;
  background: var(--deconsta-paper-claro);
  cursor: pointer;
}
label.elegido {
  border-color: var(--deconsta-primary);
  box-shadow: inset 0 0 0 1px var(--deconsta-primary);
}
input {
  margin: 3px 0 0;
  accent-color: var(--deconsta-primary);
}
.nombre {
  display: block;
  font-weight: 600;
}
.pide {
  display: block;
  margin-top: 2px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.45;
}
.tipos:disabled label {
  cursor: not-allowed;
  opacity: 0.65;
}
.tipos:disabled label.elegido {
  opacity: 1;
}
.bloqueo {
  margin: 0 0 10px;
  padding: 10px 12px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  font-size: var(--texto-sm);
}
.error {
  margin: 6px 0 0;
  color: var(--deconsta-error);
  font-size: var(--texto-sm);
}
@media (max-width: 520px) {
  .opciones {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
