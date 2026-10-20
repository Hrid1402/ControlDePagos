<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useFieldValue, useSetFieldValue } from 'vee-validate'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import { consultarDisponibilidad } from '@/api/asistentes'
import { esquemaUsername, LARGO_MAXIMO_USERNAME, LARGO_MINIMO_USERNAME } from '@/config/reglas'

// H03 CA06: el usuario elegido se comprueba mientras se escribe. La comprobación no lo reserva:
// si otro lo toma antes de crear, el 409 del envío vuelve a marcar el campo.
const ESPERA_MS = 400
const valor = useFieldValue<string>('username')
const fijar = useSetFieldValue<string>('username')
const estado = ref<'quieto' | 'comprobando' | 'libre' | 'ocupado' | 'error'>('quieto')
const sugerencia = ref<string | null>(null)
let temporizador: ReturnType<typeof setTimeout> | undefined
let consulta: AbortController | undefined

watch(valor, (texto) => {
  clearTimeout(temporizador)
  consulta?.abort()
  sugerencia.value = null
  if (!esquemaUsername.safeParse(texto ?? '').success) {
    estado.value = 'quieto'
    return
  }
  estado.value = 'comprobando'
  temporizador = setTimeout(async () => {
    consulta = new AbortController()
    try {
      const r = await consultarDisponibilidad(texto.trim(), consulta.signal)
      estado.value = r.disponible ? 'libre' : 'ocupado'
      sugerencia.value = r.sugerencia
    } catch (error: unknown) {
      if ((error as { code?: string } | null)?.code !== 'CANCELADA') estado.value = 'error'
    }
  }, ESPERA_MS)
})
onBeforeUnmount(() => {
  clearTimeout(temporizador)
  consulta?.abort()
})
</script>

<template>
  <div class="campo-usuario">
    <CampoTexto
      nombre="username"
      etiqueta="Nombre de usuario"
      autocomplete="off"
      autocapitalize="none"
      spellcheck="false"
      :ayuda="`De ${LARGO_MINIMO_USERNAME} a ${LARGO_MAXIMO_USERNAME} caracteres: letras sin tilde, números, punto, guion o guion bajo.`"
    />
    <p class="disponibilidad" :class="estado" aria-live="polite">
      <template v-if="estado === 'comprobando'">Comprobando…</template>
      <template v-else-if="estado === 'libre'">Disponible</template>
      <template v-else-if="estado === 'ocupado'">
        Ya está en uso.
        <button v-if="sugerencia" type="button" class="usar" @click="fijar(sugerencia)">
          Usar {{ sugerencia }}
        </button>
      </template>
      <template v-else-if="estado === 'error'">
        No pudimos comprobarlo; lo revisaremos al crear la cuenta.
      </template>
    </p>
  </div>
</template>

<style scoped>
.campo-usuario {
  display: grid;
  gap: 6px;
}
.disponibilidad {
  min-height: 1.5em;
  margin: 0;
  font-size: var(--texto-sm);
  color: var(--deconsta-muted);
}
.disponibilidad.libre {
  color: var(--deconsta-primary);
  font-weight: 600;
}
.disponibilidad.ocupado {
  color: var(--deconsta-error);
  font-weight: 600;
}
.usar {
  margin-left: 6px;
  padding: 2px 4px;
  border: 0;
  background: none;
  color: var(--deconsta-primary);
  font-weight: 700;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}
.usar:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
</style>
