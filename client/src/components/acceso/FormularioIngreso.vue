<script setup lang="ts">
import { watch } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import CampoAcceso from './CampoAcceso.vue'
import type { CredencialesIngreso } from '@/types/acceso'
const props = withDefaults(
  defineProps<{ cargando?: boolean; bloqueado?: boolean; mostrarVacios?: boolean }>(),
  { cargando: false, bloqueado: false, mostrarVacios: false },
)
const emit = defineEmits<{ enviar: [datos: CredencialesIngreso]; recuperar: [] }>()
const { handleSubmit, setErrors, setFieldValue } = useForm({
  initialValues: { username: '', contrasena: '' },
  validationSchema: toTypedSchema(
    z.object({
      username: z.string().trim().min(1, 'Escribe tu usuario.'),
      contrasena: z.string().min(1, 'Escribe tu contraseña.'),
    }),
  ),
})
watch(
  () => props.mostrarVacios,
  (vacio) => {
    if (vacio) setErrors({ username: 'Escribe tu usuario.', contrasena: 'Escribe tu contraseña.' })
  },
  { immediate: true },
)
const enfocar = (nombre: string) =>
  document.querySelector<HTMLInputElement>(`input[name="${nombre}"]`)?.focus()
const enviar = handleSubmit(
  (datos) => {
    if (!props.cargando && !props.bloqueado) emit('enviar', datos)
  },
  ({ errors }) => {
    // El primer campo con error en el orden del formulario, no en el del objeto de errores.
    const nombre = ['username', 'contrasena'].find((campo) => campo in errors)
    if (nombre) enfocar(nombre)
  },
)
defineExpose({
  marcarError(campo: 'username' | 'contrasena', mensaje: string) {
    setErrors({ [campo]: mensaje })
    enfocar(campo)
  },
  /** Tras credenciales incorrectas se conserva el usuario y se vuelve a pedir la contraseña. */
  pedirContrasena() {
    setFieldValue('contrasena', '', false)
    enfocar('contrasena')
  },
})
</script>
<template>
  <section class="hoja-acceso" aria-labelledby="titulo-formulario">
    <div class="titulo-hoja">
      <h2 id="titulo-formulario">Entra a tu espacio.</h2>
      <p>Con el usuario que recibiste.</p>
    </div>
    <slot name="aviso" />
    <form class="campos-ingreso" novalidate :aria-busy="cargando" @submit="enviar">
      <fieldset :disabled="cargando || bloqueado">
        <CampoAcceso
          nombre="username"
          etiqueta="Usuario"
          placeholder="Tu nombre de usuario"
          autocomplete="username"
          autocapitalize="none"
          :spellcheck="false"
        />
        <CampoAcceso
          nombre="contrasena"
          etiqueta="Contraseña"
          secreto
          placeholder="Tu contraseña"
          autocomplete="current-password"
        />
        <button type="submit" class="boton-acceso" :disabled="cargando || bloqueado">
          <span v-if="cargando" class="espera-acceso" aria-hidden="true" />{{
            cargando ? 'Entrando…' : 'Entrar'
          }}
        </button>
      </fieldset>
    </form>
    <div class="pie-hoja">
      <button type="button" class="enlace-acceso" @click="emit('recuperar')">
        Olvidé mi contraseña
      </button>
      <p>¿Aún no tienes acceso? Solicítalo al administrador.</p>
    </div>
  </section>
</template>
<style scoped>
.campos-ingreso fieldset {
  display: grid;
  grid-template-columns: 1fr 1.15fr 0.55fr;
  gap: 30px;
  align-items: start;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}
.campos-ingreso .boton-acceso {
  margin-top: 28px;
}
@media (max-width: 800px) {
  .campos-ingreso fieldset {
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
  .campos-ingreso .boton-acceso {
    grid-column: 1 / -1;
    margin-top: 0;
  }
}
@media (max-width: 560px) {
  .campos-ingreso fieldset {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }
}
</style>
