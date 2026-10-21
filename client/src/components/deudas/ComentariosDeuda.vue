<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import { fechaHora, LARGO_COMENTARIO, type ComentarioDeuda } from './detalle'

// H17 CA06: conversación entre gerente y asistente sobre la deuda. Sin permiso de comentar (deuda
// anulada) se lee y no se escribe. Quien la usa envía el texto y limpia al recibir el comentario.
const props = withDefaults(
  defineProps<{
    comentarios: ComentarioDeuda[]
    puedeComentar: boolean
    enviando?: boolean
    error?: string | null
  }>(),
  { enviando: false, error: null },
)
const emit = defineEmits<{ comentar: [texto: string] }>()

const texto = ref('')
const restante = computed(() => LARGO_COMENTARIO - texto.value.length)
const valido = computed(() => texto.value.trim().length > 0 && restante.value >= 0)

function enviar() {
  if (!valido.value || props.enviando) return
  emit('comentar', texto.value.trim())
}
defineExpose({ limpiar: () => (texto.value = '') })
</script>

<template>
  <section class="comentarios" aria-labelledby="comentarios-titulo">
    <h2 id="comentarios-titulo">Comentarios</h2>
    <ol v-if="comentarios.length" class="hilo">
      <li v-for="c in comentarios" :key="c.id" :class="{ propio: c.propio }">
        <p class="autor">
          {{ c.propio ? 'Tú' : c.autor }}
          <span class="rol">{{ c.rol === 'gerente' ? 'Gerente' : 'Asistente' }}</span>
        </p>
        <p class="burbuja">{{ c.texto }}</p>
        <time :datetime="c.creado_en">{{ fechaHora(c.creado_en) }}</time>
      </li>
    </ol>
    <p v-else class="sin-comentarios">
      {{
        puedeComentar
          ? 'Escribe aquí lo que la otra persona deba saber: un monto distinto, dónde pagaste o una duda.'
          : 'Esta deuda no tiene comentarios.'
      }}
    </p>
    <form v-if="puedeComentar" class="escribir" @submit.prevent="enviar">
      <label for="comentario-texto" class="lector">Nuevo comentario</label>
      <textarea
        id="comentario-texto"
        v-model="texto"
        rows="3"
        :maxlength="LARGO_COMENTARIO + 50"
        placeholder="Escribe un comentario"
        :aria-invalid="restante < 0"
        aria-describedby="comentario-ayuda"
        @keydown.enter.meta.prevent="enviar"
        @keydown.enter.ctrl.prevent="enviar"
      ></textarea>
      <div class="pie">
        <span id="comentario-ayuda" :class="{ excedido: restante < 0 }">
          {{
            restante < 0
              ? `Sobran ${-restante} caracteres`
              : `${texto.length} de ${LARGO_COMENTARIO}`
          }}
        </span>
        <Button
          type="submit"
          label="Enviar"
          icon="pi pi-send"
          size="small"
          :loading="enviando"
          :disabled="!valido"
        />
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </form>
  </section>
</template>

<style scoped>
h2 {
  margin: 0 0 14px;
  font-size: var(--texto-md);
}
.hilo {
  display: grid;
  gap: 14px;
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}
.hilo li {
  display: grid;
  justify-items: start;
  gap: 4px;
  max-width: 92%;
}
.hilo li.propio {
  justify-items: end;
  margin-left: auto;
}
.hilo p {
  margin: 0;
}
.autor {
  font-size: var(--texto-xs);
  font-weight: 700;
}
.rol {
  margin-left: 6px;
  color: var(--deconsta-muted);
  font-weight: 500;
}
.burbuja {
  padding: 10px 14px;
  border-radius: 4px 14px 14px 14px;
  background: #fff;
  border: 1px solid var(--deconsta-linea);
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.propio .burbuja {
  border-color: transparent;
  border-radius: 14px 4px 14px 14px;
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
time {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
.sin-comentarios {
  margin: 0 0 14px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.55;
}
textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #7b8798;
  border-radius: var(--radio-control);
  background: #fff;
  color: var(--deconsta-ink);
  font: inherit;
  line-height: 1.5;
  resize: vertical;
}
textarea:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 1px;
}
textarea[aria-invalid='true'] {
  border-color: var(--deconsta-error);
}
.pie {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
.excedido,
.error {
  color: var(--deconsta-error);
  font-weight: 700;
}
.error {
  margin: 8px 0 0;
  font-size: var(--texto-sm);
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
