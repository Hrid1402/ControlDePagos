<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'
import ResumenCuenta from '@/components/cuenta/ResumenCuenta.vue'
import SeccionDatos from '@/components/cuenta/SeccionDatos.vue'
import SeccionUsuario from '@/components/cuenta/SeccionUsuario.vue'
import SeccionContrasena from '@/components/cuenta/SeccionContrasena.vue'
import { obtenerPerfil } from '@/api/acceso'
import type { PerfilCuenta, SenalesCuenta } from '@/types/cuenta'

// Diseño de Mi cuenta (TASK-6, H02). Lee el perfil real; guardar cada sección se conecta en
// TASK-9, así que por ahora ningún envío simula un cambio guardado.
const route = useRoute()
const perfil = ref<PerfilCuenta | null>(null)
const estado = ref<'cargando' | 'lista' | 'error'>('cargando')

async function cargar() {
  estado.value = 'cargando'
  try {
    perfil.value = await obtenerPerfil()
    estado.value = 'lista'
  } catch {
    estado.value = 'error'
  }
}
onMounted(cargar)

async function sinConectar(): Promise<never> {
  throw { detail: 'Todavía no podemos guardar este cambio. Lo que escribiste sigue aquí.' }
}

// Solo en desarrollo, /…/cuenta?revision=1 fuerza los estados del diseño sobre el perfil real,
// sin inventar datos: vaciar campos, contador y aviso de contraseña inicial.
const revisando = computed(() => import.meta.env.DEV && route.query.revision === '1')
const revision = ref({ estado: 'real', incompleto: false, contador: 'api', inicial: 'api' })
const estadoVisible = computed(() =>
  revisando.value && revision.value.estado !== 'real' ? revision.value.estado : estado.value,
)
const perfilVisible = computed(() =>
  perfil.value && revisando.value && revision.value.incompleto
    ? { ...perfil.value, correo: null, celular: null, tipo_documento: null, numero_documento: null }
    : perfil.value,
)
const senales = computed<SenalesCuenta>(() => {
  const real: SenalesCuenta = {
    cambiosRestantes: perfil.value?.cambios_restantes ?? null,
    contrasenaInicial: perfil.value?.contrasena_inicial ?? null,
  }
  if (!revisando.value) return real
  const { contador, inicial } = revision.value
  return {
    cambiosRestantes: contador === 'api' ? real.cambiosRestantes : Number(contador),
    contrasenaInicial: inicial === 'api' ? real.contrasenaInicial : inicial === 'si',
  }
})
</script>

<template>
  <div class="mi-cuenta">
    <header class="encabezado">
      <h1>Mi cuenta</h1>
      <p>Consulta y actualiza tus datos de acceso y contacto.</p>
    </header>

    <div v-if="estadoVisible === 'cargando'" class="cuerpo" aria-busy="true">
      <p class="lector" role="status">Cargando tu cuenta…</p>
      <div class="marcador marcador--resumen"></div>
      <div class="marcadores">
        <div v-for="n in 3" :key="n" class="marcador"></div>
      </div>
    </div>

    <div v-else-if="estadoVisible === 'error' || !perfilVisible" class="fallo" role="alert">
      <h2>No pudimos cargar tu cuenta.</h2>
      <p>Revisa tu conexión e inténtalo otra vez. No mostramos datos que no pudimos confirmar.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="cargar" />
    </div>

    <div v-else class="cuerpo">
      <div class="lateral">
        <ResumenCuenta :perfil="perfilVisible" :senales="senales" />
      </div>
      <div class="secciones">
        <SeccionDatos
          :key="String(revision.incompleto)"
          :perfil="perfilVisible"
          :guardar="sinConectar"
        />
        <SeccionUsuario
          :username="perfilVisible.username"
          :cambios-restantes="senales.cambiosRestantes"
          :guardar="sinConectar"
        />
        <SeccionContrasena :guardar="sinConectar" />
      </div>
    </div>

    <details v-if="revisando" class="revision">
      <summary>Revisar estados del diseño</summary>
      <p>Solo en desarrollo. Cambia lo que se muestra; no guarda nada.</p>
      <label>
        Pantalla
        <select v-model="revision.estado">
          <option value="real">Según la API</option>
          <option value="cargando">Cargando</option>
          <option value="error">Error de carga</option>
        </select>
      </label>
      <label><input v-model="revision.incompleto" type="checkbox" /> Perfil incompleto</label>
      <label>
        Cambios de usuario
        <select v-model="revision.contador">
          <option value="api">Según la API</option>
          <option value="2">Quedan 2</option>
          <option value="1">Queda 1</option>
          <option value="0">Agotados</option>
        </select>
      </label>
      <label>
        Contraseña inicial
        <select v-model="revision.inicial">
          <option value="api">Según la API</option>
          <option value="si">Sí</option>
          <option value="no">No</option>
        </select>
      </label>
    </details>
  </div>
</template>

<style scoped>
.encabezado {
  max-width: 62ch;
  margin-bottom: clamp(28px, 4vw, 48px);
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.encabezado p {
  margin: 12px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
/* Escritorio: el resumen fijo a la izquierda acompaña la lectura de las tres secciones. */
.cuerpo {
  display: grid;
  grid-template-columns: minmax(240px, 300px) minmax(0, 760px);
  gap: clamp(32px, 5vw, 80px);
  align-items: start;
}
.lateral {
  position: sticky;
  top: 24px;
}
.secciones {
  display: grid;
  gap: 48px;
}
.secciones :deep(.seccion-cuenta + .seccion-cuenta) {
  padding-top: 48px;
  border-top: 1px solid var(--deconsta-linea);
}
.secciones :deep(.seccion-cuenta) {
  scroll-margin-top: 24px;
}
.secciones :deep(.seccion-cuenta > header) {
  margin-bottom: 24px;
}
.secciones :deep(.seccion-cuenta h2) {
  margin: 0;
  font-size: var(--texto-lg);
  font-weight: 700;
  letter-spacing: -0.015em;
}
.secciones :deep(.seccion-cuenta > header p) {
  margin: 6px 0 0;
  color: var(--deconsta-muted);
  line-height: 1.6;
}
.secciones :deep(.aviso-seccion) {
  margin: 0 0 24px;
  padding: 12px 16px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  line-height: 1.6;
}
.marcadores {
  display: grid;
  gap: 32px;
}
.marcador {
  height: 180px;
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
.marcador--resumen {
  height: 280px;
}
@keyframes brillo {
  to {
    background-position: -200% 0;
  }
}
.fallo {
  max-width: 52ch;
  padding: 28px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo h2 {
  margin: 0;
  font-size: var(--texto-lg);
}
.fallo p {
  margin: 8px 0 20px;
  line-height: 1.6;
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
.revision {
  margin-top: 56px;
  padding: 16px 20px;
  border: 1px dashed var(--deconsta-muted);
  border-radius: var(--radio-control);
  font-size: var(--texto-sm);
}
.revision summary {
  font-weight: 700;
  cursor: pointer;
}
.revision label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 12px 24px 0 0;
}
@media (max-width: 959px) {
  .cuerpo {
    grid-template-columns: minmax(0, 1fr);
  }
  .lateral {
    position: static;
  }
  .marcador--resumen {
    height: 140px;
  }
}
</style>
