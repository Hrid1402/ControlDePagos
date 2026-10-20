<script setup lang="ts">
import { computed } from 'vue'
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import CampoAcceso from './CampoAcceso.vue'
import { esquemaContrasenaNueva, requisitosContrasena } from '@/config/reglas'
const props = defineProps<{ cargando?: boolean }>()
const emit = defineEmits<{ enviar: [contrasena: string]; volver: [] }>()
const { values, handleSubmit, setErrors } = useForm({
  initialValues: { nueva: '', confirmar: '' },
  validationSchema: toTypedSchema(
    z
      .object({
        nueva: esquemaContrasenaNueva,
        confirmar: z.string().min(1, 'Confirma la contraseña.'),
      })
      .refine((v) => v.nueva === v.confirmar, {
        message: 'Las contraseñas deben coincidir.',
        path: ['confirmar'],
      }),
  ),
})
const requisitos = computed(() =>
  requisitosContrasena.map((regla) => ({
    etiqueta: regla.etiqueta,
    cumple: regla.cumple(values.nueva || ''),
  })),
)
const enfocar = (campo: string) =>
  document.querySelector<HTMLInputElement>(`input[name="${campo}"]`)?.focus()
const enviar = handleSubmit(
  ({ nueva }) => {
    if (!props.cargando) emit('enviar', nueva)
  },
  ({ errors }) => {
    const campo = ['nueva', 'confirmar'].find((nombre) => nombre in errors)
    if (campo) enfocar(campo)
  },
)
defineExpose({
  marcarError(campo: 'nueva' | 'confirmar', mensaje: string) {
    setErrors({ [campo]: mensaje })
    enfocar(campo)
  },
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
