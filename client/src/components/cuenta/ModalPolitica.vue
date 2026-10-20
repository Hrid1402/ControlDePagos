<script setup lang="ts">
import { onMounted, ref } from 'vue'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import { aceptarPolitica, obtenerPolitica } from '@/api/acceso'
import type { PerfilCuenta, PoliticaPrivacidad } from '@/types/cuenta'
import type { ErrorApi } from '@/types/api'

// H02 CA10: en el primer ingreso, o cuando cambia la versión, se acepta la política vigente. No se
// cierra sin aceptar; la única salida es cerrar sesión. La aceptación vale solo si el servidor
// la confirma.
const emit = defineEmits<{ aceptada: [perfil: PerfilCuenta]; salir: [] }>()
const politica = ref<PoliticaPrivacidad | null>(null)
const estado = ref<'cargando' | 'lista' | 'error'>('cargando')
const aceptando = ref(false)
const aviso = ref('')

async function cargar() {
  estado.value = 'cargando'
  try {
    politica.value = await obtenerPolitica()
    estado.value = 'lista'
  } catch {
    estado.value = 'error'
  }
}
onMounted(cargar)

async function aceptar() {
  if (!politica.value || aceptando.value) return
  aceptando.value = true
  aviso.value = ''
  try {
    emit('aceptada', await aceptarPolitica(politica.value.version))
  } catch (error: unknown) {
    const datos = error as Partial<ErrorApi> | null
    if (datos?.code === 'POLITICA_DESACTUALIZADA') {
      aviso.value = 'La política cambió mientras la leías. Revisa la versión vigente.'
      await cargar()
    } else {
      aviso.value = 'No pudimos registrar tu aceptación. Inténtalo otra vez.'
    }
  } finally {
    aceptando.value = false
  }
}

function fecha(iso: string) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('es-PE', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}
</script>

<template>
  <Dialog
    visible
    modal
    :closable="false"
    :close-on-escape="false"
    :draggable="false"
    :style="{ width: 'min(720px, calc(100vw - 32px))' }"
    aria-labelledby="politica-titulo"
    class="modal-politica"
  >
    <template #header>
      <div class="cabecera">
        <h2 id="politica-titulo">Antes de continuar</h2>
        <p>
          Lee cómo tratamos tus datos personales. Para usar Control de Pagos necesitas aceptar esta
          política.
        </p>
      </div>
    </template>

    <div v-if="estado === 'cargando'" class="estado" role="status">Cargando la política…</div>
    <div v-else-if="estado === 'error'" class="estado" role="alert">
      <p>No pudimos cargar la política de privacidad.</p>
      <Button label="Reintentar" icon="pi pi-refresh" text @click="cargar" />
    </div>
    <article v-else-if="politica" class="texto" tabindex="0" aria-label="Política de privacidad">
      <p class="version">
        Versión {{ politica.version }}, vigente desde el {{ fecha(politica.vigente_desde) }}.
      </p>
      <section v-for="seccion in politica.secciones" :key="seccion.titulo">
        <h3>{{ seccion.titulo }}</h3>
        <p v-for="(parrafo, i) in seccion.parrafos" :key="i">{{ parrafo }}</p>
      </section>
    </article>
    <p v-if="aviso" class="aviso" role="alert">{{ aviso }}</p>

    <template #footer>
      <Button label="Cerrar sesión" text @click="emit('salir')" />
      <Button
        label="Aceptar y continuar"
        :loading="aceptando"
        :disabled="estado !== 'lista'"
        @click="aceptar"
      />
    </template>
  </Dialog>
</template>

<style scoped>
.cabecera h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.cabecera p {
  margin: 6px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  line-height: 1.6;
}
.texto {
  max-height: min(55vh, 520px);
  overflow-y: auto;
  padding: 4px 16px 4px 0;
  line-height: 1.65;
  overscroll-behavior: contain;
}
.texto:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 4px;
}
.version {
  margin: 0 0 8px;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
h3 {
  margin: 20px 0 6px;
  font-size: var(--texto-base);
  font-weight: 700;
}
.texto p {
  margin: 0 0 8px;
  max-width: 68ch;
}
.estado {
  padding: 24px 0;
}
.aviso {
  margin: 16px 0 0;
  padding: 12px 16px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
</style>
