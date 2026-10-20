<script setup lang="ts">
import { computed } from 'vue'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import { LARGO_MAXIMO_USERNAME, LARGO_MINIMO_USERNAME } from '@/config/reglas'
import { esquemaCambioUsuario } from '@/types/cuenta'

const props = defineProps<{
  username: string
  /** null mientras la API no informe el contador: el cambio espera el dato real. */
  cambiosRestantes: number | null
  guardar: (valores: Record<string, unknown>) => Promise<unknown>
}>()
const esquema = computed(() => esquemaCambioUsuario(props.username))
const proximoMes = computed(() => {
  const hoy = new Date()
  const fecha = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 1)
  return fecha.toLocaleDateString('es-PE', { day: 'numeric', month: 'long' })
})
const contador = computed(() => {
  const restantes = props.cambiosRestantes
  if (restantes === null)
    return 'Podrás cambiarlo cuando confirmemos cuántos cambios te quedan este mes.'
  if (restantes === 0)
    return `Ya usaste tus cambios de este mes. Podrás cambiarlo otra vez desde el ${proximoMes.value}.`
  return restantes === 1
    ? 'Te queda 1 cambio este mes.'
    : `Te quedan ${restantes} cambios este mes.`
})
</script>

<template>
  <section id="usuario" class="seccion-cuenta" aria-labelledby="usuario-titulo">
    <header>
      <h2 id="usuario-titulo">Usuario</h2>
      <p>
        Ingresas como <strong class="usuario-actual">{{ username }}</strong
        >. Puedes cambiarlo hasta 2 veces al mes.
      </p>
    </header>
    <p
      class="contador"
      :class="{ agotado: cambiosRestantes === 0 || cambiosRestantes === null }"
      role="status"
    >
      {{ contador }}
    </p>
    <FormularioBase
      :key="username"
      :esquema="esquema"
      :valores-iniciales="{ username: '' }"
      :guardar="guardar"
      texto-boton="Cambiar usuario"
      mensaje-exito="Desde ahora debes ingresar con tu nuevo usuario."
      :bloqueado="!cambiosRestantes"
    >
      <CampoTexto
        nombre="username"
        etiqueta="Nuevo usuario"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
        :ayuda="`De ${LARGO_MINIMO_USERNAME} a ${LARGO_MAXIMO_USERNAME} caracteres: letras sin tilde, números, punto, guion o guion bajo.`"
      />
    </FormularioBase>
  </section>
</template>

<style scoped>
.usuario-actual {
  font-weight: 700;
  overflow-wrap: anywhere;
}
.contador {
  margin: 0 0 20px;
  font-weight: 600;
}
.contador.agotado {
  color: var(--deconsta-muted);
  font-weight: 500;
}
</style>
