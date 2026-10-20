<script setup lang="ts">
import { computed, ref } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { useConfirm } from 'primevue/useconfirm'
import type { Credenciales } from '@/types/asistentes'

// H03 CA08 y CA16: la contraseña se muestra una sola vez. Vive solo en este diálogo: no se guarda
// en el estado, el almacenamiento ni la URL, y al cerrar se pierde.
const props = defineProps<{
  credenciales: Credenciales
  motivo: 'alta' | 'restablecimiento'
  /** Tras crear una cuenta inactiva se ofrece activarla (CA09). */
  ofrecerActivar?: boolean
}>()
const emit = defineEmits<{ cerrar: []; activar: [] }>()
const confirmacion = useConfirm()
const visible = ref(false)
const copiado = ref<'usuario' | 'contrasena' | 'ambos' | null>(null)
const fallo = ref('')
const puedeCompartir = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

const titulo = computed(() =>
  props.motivo === 'alta'
    ? `Credenciales de ${props.credenciales.nombre}`
    : `Nueva contraseña de ${props.credenciales.nombre}`,
)
const texto = computed(
  () =>
    `Usuario: ${props.credenciales.username}\nContraseña: ${props.credenciales.contrasena}\n` +
    'Cámbiala en Mi cuenta al ingresar por primera vez.',
)

async function copiar(que: 'usuario' | 'contrasena' | 'ambos') {
  const valor =
    que === 'usuario'
      ? props.credenciales.username
      : que === 'contrasena'
        ? props.credenciales.contrasena
        : texto.value
  fallo.value = ''
  try {
    await navigator.clipboard.writeText(valor)
    copiado.value = que
  } catch {
    copiado.value = null
    fallo.value = 'No pudimos copiar. Selecciona el texto y cópialo a mano.'
  }
}

async function compartir() {
  try {
    await navigator.share({ title: 'Acceso a Control de Pagos', text: texto.value })
  } catch {
    // Cancelar el menú de compartir no es un error; las credenciales siguen a la vista.
  }
}

function pedirCierre(luego: 'cerrar' | 'activar' = 'cerrar') {
  confirmacion.require({
    header: 'Cerrar las credenciales',
    message: 'Después de cerrar, no podrás volver a ver esta contraseña.',
    acceptLabel: 'Cerrar de todas formas',
    rejectLabel: 'Volver a credenciales',
    defaultFocus: 'reject',
    rejectProps: { text: true },
    accept: () => (luego === 'activar' ? emit('activar') : emit('cerrar')),
  })
}
</script>

<template>
  <Dialog
    visible
    modal
    dismissable-mask
    :header="titulo"
    :draggable="false"
    :style="{ width: 'min(520px, calc(100vw - 24px))' }"
    @update:visible="pedirCierre()"
  >
    <p class="aviso">Guárdalas ahora. La contraseña no volverá a mostrarse.</p>
    <dl class="credencial">
      <div class="dato">
        <dt>Usuario</dt>
        <dd>
          <output class="valor">{{ credenciales.username }}</output>
          <span class="botones">
            <Button
              :label="copiado === 'usuario' ? 'Copiado' : 'Copiar usuario'"
              :icon="copiado === 'usuario' ? 'pi pi-check' : 'pi pi-copy'"
              size="small"
              text
              @click="copiar('usuario')"
            />
          </span>
        </dd>
      </div>
      <div class="dato">
        <dt>Contraseña</dt>
        <dd>
          <output class="valor" :class="{ oculta: !visible }">
            {{ visible ? credenciales.contrasena : '•'.repeat(credenciales.contrasena.length) }}
          </output>
          <span class="botones">
            <Button
              :label="visible ? 'Ocultar' : 'Mostrar'"
              :icon="visible ? 'pi pi-eye-slash' : 'pi pi-eye'"
              :aria-label="visible ? 'Ocultar contraseña' : 'Mostrar contraseña'"
              size="small"
              text
              @click="visible = !visible"
            />
            <Button
              :label="copiado === 'contrasena' ? 'Copiada' : 'Copiar contraseña'"
              :icon="copiado === 'contrasena' ? 'pi pi-check' : 'pi pi-copy'"
              size="small"
              text
              @click="copiar('contrasena')"
            />
          </span>
        </dd>
      </div>
    </dl>
    <p v-if="fallo" class="fallo" role="alert">{{ fallo }}</p>
    <p v-else class="lector" aria-live="polite">{{ copiado ? 'Copiado al portapapeles.' : '' }}</p>

    <template #footer>
      <Button v-if="ofrecerActivar" label="Activar ahora" text @click="pedirCierre('activar')" />
      <Button
        v-if="puedeCompartir"
        label="Compartir credenciales"
        icon="pi pi-share-alt"
        outlined
        @click="compartir"
      />
      <Button
        v-else
        :label="copiado === 'ambos' ? 'Copiadas' : 'Copiar ambos'"
        icon="pi pi-copy"
        outlined
        @click="copiar('ambos')"
      />
      <Button label="Listo" @click="pedirCierre()" />
    </template>
  </Dialog>
</template>

<style scoped>
.aviso {
  margin: 0 0 20px;
  padding: 12px 14px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  line-height: 1.6;
}
/* La credencial se presenta como una tarjeta de acceso: franja verde y la esquina de la marca. */
.credencial {
  display: grid;
  margin: 0;
  overflow: hidden;
  border-radius: 5px 24px 5px 5px;
  background: var(--deconsta-paper);
  box-shadow: inset 4px 0 0 var(--deconsta-primary);
}
.dato {
  display: grid;
  gap: 6px;
  padding: 16px 18px 12px 24px;
}
.dato + .dato {
  border-top: 1px solid var(--deconsta-linea);
}
dt {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
dd {
  display: grid;
  gap: 6px;
  margin: 0;
}
.botones {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-left: -10px;
}
/* Monoespaciada a propósito: distingue l de 1 y O de 0 al dictar o transcribir. */
.valor {
  min-width: 0;
  font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  overflow-wrap: anywhere;
  user-select: all;
}
.valor.oculta {
  letter-spacing: 0.12em;
  user-select: none;
}
.fallo {
  margin: 14px 0 0;
  color: var(--deconsta-error);
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
</style>
