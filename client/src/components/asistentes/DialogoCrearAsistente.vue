<script setup lang="ts">
import { computed } from 'vue'
import Dialog from 'primevue/dialog'
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import CampoOpciones from '@/components/formularios/CampoOpciones.vue'
import CampoUsuarioDisponible from './CampoUsuarioDisponible.vue'
import { crearAsistente } from '@/api/asistentes'
import { esquemaCrearAsistente, type Credenciales } from '@/types/asistentes'

// H03 CA04 a CA09. Si ya hay una activa, la nueva se crea inactiva: la pantalla fija
// activar_ahora de forma expresa y nunca reemplaza a la actual sin confirmarlo.
const props = defineProps<{ activa: string | null }>()
const emit = defineEmits<{
  creada: [credenciales: Credenciales & { estado: string }]
  cerrar: []
}>()

const MODOS = [
  { valor: 'generar', etiqueta: 'Generar' },
  { valor: 'elegir', etiqueta: 'Elegir' },
]
const textoBoton = computed(() => (props.activa ? 'Crear asistente inactiva' : 'Crear y activar'))

async function guardar(valores: Record<string, unknown>) {
  const creada = await crearAsistente({
    nombres: String(valores.nombres).trim(),
    apellidos: String(valores.apellidos).trim(),
    username: valores.modo_usuario === 'elegir' ? String(valores.username).trim() : undefined,
    contrasena: valores.modo_contrasena === 'elegir' ? String(valores.contrasena) : undefined,
    activar_ahora: !props.activa,
  })
  emit('creada', creada)
}
</script>

<template>
  <Dialog
    visible
    modal
    header="Crear asistente"
    :draggable="false"
    :style="{ width: 'min(560px, calc(100vw - 24px))' }"
    @update:visible="emit('cerrar')"
  >
    <p class="explicacion">
      Indica sus nombres y apellidos. Podrá completar sus datos personales al ingresar.
    </p>
    <FormularioBase
      :esquema="esquemaCrearAsistente"
      :valores-iniciales="{
        nombres: '',
        apellidos: '',
        modo_usuario: 'generar',
        username: '',
        modo_contrasena: 'generar',
        contrasena: '',
      }"
      :guardar="guardar"
      :texto-boton="textoBoton"
      mensaje-exito="La cuenta se creó."
    >
      <template #default="{ valores }">
        <div class="nombre">
          <CampoTexto nombre="nombres" etiqueta="Nombres" autocomplete="off" />
          <CampoTexto nombre="apellidos" etiqueta="Apellidos" autocomplete="off" />
        </div>
        <div class="credencial">
          <CampoOpciones nombre="modo_usuario" etiqueta="Usuario" :opciones="MODOS" />
          <p v-if="valores.modo_usuario === 'generar'" class="nota">
            Usaremos la inicial de su nombre y su primer apellido, como lgomez. Si ya existe, le
            agregamos un número.
          </p>
          <CampoUsuarioDisponible v-else />
        </div>
        <div class="credencial">
          <CampoOpciones nombre="modo_contrasena" etiqueta="Contraseña" :opciones="MODOS" />
          <p v-if="valores.modo_contrasena === 'generar'" class="nota">
            La verás una sola vez, después de crear la cuenta.
          </p>
          <CampoTexto
            v-else
            nombre="contrasena"
            etiqueta="Contraseña inicial"
            tipo="password"
            autocomplete="new-password"
            ayuda="Al menos 8 caracteres, con mayúscula, minúscula, número y símbolo."
          />
        </div>
        <p class="efecto" :class="{ inactiva: !!activa }" role="note">
          <template v-if="activa">
            Se creará inactiva, porque {{ activa }} está activa. Podrás activarla después.
          </template>
          <template v-else>Se creará activa y podrá atender tus pagos desde que ingrese.</template>
        </p>
      </template>
    </FormularioBase>
  </Dialog>
</template>

<style scoped>
.explicacion {
  margin: 0 0 20px;
  color: var(--deconsta-muted);
  line-height: 1.6;
}
.nombre {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
}
.credencial {
  display: grid;
  gap: 12px;
  padding-top: 20px;
  border-top: 1px solid var(--deconsta-linea);
}
.nota {
  margin: 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.efecto {
  margin: 0;
  padding: 12px 14px;
  border-left: 3px solid var(--deconsta-primary);
  background: var(--deconsta-realce);
  font-size: var(--texto-sm);
  line-height: 1.6;
}
.efecto.inactiva {
  border-color: var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
}
@media (max-width: 520px) {
  .nombre {
    grid-template-columns: 1fr;
  }
}
</style>
