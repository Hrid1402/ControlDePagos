<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import CampoAcceso from './CampoAcceso.vue'
const props = defineProps<{ cargando?: boolean }>()
const emit = defineEmits<{ enviar: [correo: string]; volver: [] }>()
const { handleSubmit } = useForm({
  initialValues: { correo: '' },
  validationSchema: toTypedSchema(
    z.object({ correo: z.string().trim().email('Escribe un correo válido.') }),
  ),
})
const enviar = handleSubmit(({ correo }) => {
  if (!props.cargando) emit('enviar', correo)
})
</script>
<template>
  <section class="hoja-acceso">
    <form class="campos-recuperacion" novalidate :aria-busy="cargando" @submit="enviar">
      <CampoAcceso
        nombre="correo"
        etiqueta="Correo de tu cuenta"
        tipo="email"
        placeholder="nombre@empresa.com"
        autocomplete="email"
        :disabled="cargando"
      />
      <button class="boton-acceso" type="submit" :disabled="cargando">
        {{ cargando ? 'Enviando…' : 'Enviar enlace' }}
      </button>
    </form>
    <div class="pie-hoja">
      <button type="button" class="enlace-acceso" @click="emit('volver')">Volver al acceso</button>
      <p>Si aún no registraste un correo, contacta con quien te entregó el acceso.</p>
    </div>
  </section>
</template>
<style scoped>
.campos-recuperacion {
  display: grid;
  grid-template-columns: 1.5fr 0.6fr;
  align-items: start;
  gap: 32px;
  max-width: 940px;
}
.boton-acceso {
  margin-top: 28px;
}
@media (max-width: 640px) {
  .campos-recuperacion {
    grid-template-columns: 1fr;
    gap: 22px;
  }
  .boton-acceso {
    margin-top: 0;
  }
}
</style>
