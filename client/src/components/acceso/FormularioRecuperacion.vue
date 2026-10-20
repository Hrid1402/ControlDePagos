<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import CampoAcceso from './CampoAcceso.vue'
import { esquemaUsername } from '@/config/reglas'
const props = defineProps<{ cargando?: boolean }>()
const emit = defineEmits<{ enviar: [username: string]; volver: [] }>()
const { handleSubmit, setErrors } = useForm({
  initialValues: { username: '' },
  validationSchema: toTypedSchema(z.object({ username: esquemaUsername })),
})
const enfocar = () => document.querySelector<HTMLInputElement>('input[name="username"]')?.focus()
const enviar = handleSubmit(({ username }) => {
  if (!props.cargando) emit('enviar', username)
}, enfocar)
defineExpose({
  marcarError(mensaje: string) {
    setErrors({ username: mensaje })
    enfocar()
  },
})
</script>
<template>
  <section class="hoja-acceso">
    <form class="campos-recuperacion" novalidate :aria-busy="cargando" @submit="enviar">
      <CampoAcceso
        nombre="username"
        etiqueta="Usuario"
        placeholder="Tu nombre de usuario"
        autocomplete="username"
        autocapitalize="none"
        :spellcheck="false"
        :disabled="cargando"
      />
      <button class="boton-acceso" type="submit" :disabled="cargando">
        {{ cargando ? 'Enviando…' : 'Enviar enlace' }}
      </button>
    </form>
    <div class="pie-hoja">
      <button type="button" class="enlace-acceso" @click="emit('volver')">Volver al acceso</button>
      <p>
        El enlace llega al correo registrado en tu cuenta. Si no tienes uno, pide al gerente que la
        restablezca.
      </p>
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
