<script setup lang="ts">
import { computed } from 'vue'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import CampoSeleccion from '@/components/formularios/CampoSeleccion.vue'
import { TIPOS_DOCUMENTO, esquemaDatosPersonales, type PerfilCuenta } from '@/types/cuenta'

const props = defineProps<{
  perfil: PerfilCuenta
  guardar: (valores: Record<string, unknown>) => Promise<unknown>
}>()
const valoresIniciales = computed(() => ({
  nombres: props.perfil.nombres ?? '',
  apellidos: props.perfil.apellidos ?? '',
  tipo_documento: props.perfil.tipo_documento ?? '',
  numero_documento: props.perfil.numero_documento ?? '',
  correo: props.perfil.correo ?? '',
  celular: props.perfil.celular ?? '',
}))
const incompleto = computed(() =>
  [props.perfil.nombres, props.perfil.apellidos, props.perfil.correo, props.perfil.celular].some(
    (dato) => !dato,
  ),
)
</script>

<template>
  <section id="datos" class="seccion-cuenta" aria-labelledby="datos-titulo">
    <header>
      <h2 id="datos-titulo">Datos personales</h2>
      <p>Con ellos te identificamos y te escribimos si necesitas recuperar el acceso.</p>
    </header>
    <p v-if="incompleto" class="aviso-seccion" role="status">
      Completa tus datos personales. El correo y el celular son obligatorios.
    </p>
    <FormularioBase
      :key="perfil.id"
      :esquema="esquemaDatosPersonales"
      :valores-iniciales="valoresIniciales"
      :guardar="guardar"
      texto-boton="Guardar datos"
      mensaje-exito="Tus datos se guardaron."
      descartable
    >
      <div class="rejilla">
        <CampoTexto nombre="nombres" etiqueta="Nombres" autocomplete="given-name" />
        <CampoTexto nombre="apellidos" etiqueta="Apellidos" autocomplete="family-name" />
        <CampoSeleccion
          nombre="tipo_documento"
          etiqueta="Tipo de documento"
          :opciones="TIPOS_DOCUMENTO"
          vacia="Sin documento"
        />
        <CampoTexto nombre="numero_documento" etiqueta="Número de documento" autocomplete="off" />
        <CampoTexto nombre="correo" etiqueta="Correo" tipo="email" autocomplete="email" />
        <CampoTexto
          nombre="celular"
          etiqueta="Celular"
          tipo="tel"
          inputmode="numeric"
          autocomplete="tel-national"
          ayuda="9 dígitos, empieza con 9."
        />
      </div>
    </FormularioBase>
  </section>
</template>

<style scoped>
.rejilla {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px 28px;
  align-items: start;
}
@media (max-width: 640px) {
  .rejilla {
    grid-template-columns: 1fr;
    gap: 20px;
  }
}
</style>
