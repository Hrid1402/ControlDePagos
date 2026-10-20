<script setup lang="ts">
import { computed } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import CampoAcceso from './CampoAcceso.vue'
const props = defineProps<{ cargando?: boolean }>()
const emit = defineEmits<{ enviar: [contrasena: string]; volver: [] }>()
const reglas = [
  { etiqueta: '8 caracteres', cumple: (s: string) => s.length >= 8 },
  { etiqueta: 'Mayúscula', cumple: (s: string) => /[A-ZÁÉÍÓÚÑ]/.test(s) },
  { etiqueta: 'Minúscula', cumple: (s: string) => /[a-záéíóúñ]/.test(s) },
  { etiqueta: 'Número', cumple: (s: string) => /[0-9]/.test(s) },
  { etiqueta: 'Símbolo', cumple: (s: string) => /[^\p{L}\p{N}\s]/u.test(s) },
]
const { values, handleSubmit } = useForm({
  initialValues: { nueva: '', confirmar: '' },
  validationSchema: toTypedSchema(
    z
      .object({
        nueva: z
          .string()
          .refine(
            (valor) => reglas.every((r) => r.cumple(valor)),
            'Revisa los requisitos de tu nueva contraseña.',
          ),
        confirmar: z.string().min(1, 'Confirma la contraseña.'),
      })
      .refine((v) => v.nueva === v.confirmar, {
        message: 'Las contraseñas deben coincidir.',
        path: ['confirmar'],
      }),
  ),
})
const requisitos = computed(() =>
  reglas.map((regla) => ({ etiqueta: regla.etiqueta, cumple: regla.cumple(values.nueva || '') })),
)
const enviar = handleSubmit(({ nueva }) => {
  if (!props.cargando) emit('enviar', nueva)
})
</script>
<template>
  <section class="hoja-acceso">
    <form novalidate class="campos-clave" :aria-busy="cargando" @submit="enviar">
      <CampoAcceso
        nombre="nueva"
        etiqueta="Nueva contraseña"
        secreto
        placeholder="Elige una contraseña"
        autocomplete="new-password"
        :disabled="cargando"
      />
      <CampoAcceso
        nombre="confirmar"
        etiqueta="Confirma la nueva contraseña"
        secreto
        placeholder="Repítela una vez más"
        autocomplete="new-password"
        :disabled="cargando"
      />
      <button type="submit" class="boton-acceso" :disabled="cargando">
        {{ cargando ? 'Guardando…' : 'Guardar contraseña' }}
      </button>
    </form>
    <ul class="requisitos-clave" aria-label="Requisitos de contraseña">
      <li
        v-for="requisito in requisitos"
        :key="requisito.etiqueta"
        :class="{ cumple: requisito.cumple }"
      >
        <span aria-hidden="true">{{ requisito.cumple ? '✓' : '○' }}</span> {{ requisito.etiqueta }}
      </li>
    </ul>
    <div class="pie-hoja">
      <button type="button" class="enlace-acceso" @click="emit('volver')">Volver al acceso</button>
      <p>El enlace recibido sirve una sola vez.</p>
    </div>
  </section>
</template>
<style scoped>
.campos-clave {
  display: grid;
  grid-template-columns: 1fr 1fr 0.7fr;
  gap: 28px;
  align-items: start;
}
.boton-acceso {
  margin-top: 28px;
}
.requisitos-clave {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  list-style: none;
  margin: 18px 0 0;
  padding: 0;
  color: #52665f;
  font-size: 13px;
}
.cumple {
  color: #075a50;
  font-weight: 600;
}
@media (max-width: 800px) {
  .campos-clave {
    grid-template-columns: 1fr 1fr;
  }
  .boton-acceso {
    grid-column: 1/-1;
    margin-top: 0;
  }
}
@media (max-width: 560px) {
  .campos-clave {
    grid-template-columns: 1fr;
    gap: 22px;
  }
}
</style>
