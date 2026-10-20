<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import Button from 'primevue/button'
import EtiquetaEstado from '@/components/asistentes/EtiquetaEstado.vue'
import DialogoCredenciales from '@/components/asistentes/DialogoCredenciales.vue'
import { listarAsistentes, obtenerAsistente } from '@/api/asistentes'
import { useAccionesAsistente } from '@/composables/useAccionesAsistente'
import {
  fechaHora,
  iniciales,
  nombreDe,
  type AsistenteDetalle,
  type AsistenteFila,
  type Credenciales,
} from '@/types/asistentes'
import type { ErrorApi } from '@/types/api'

// H03 CA10 a CA17: detalle de una cuenta, su historial de activaciones y sus acciones.
const route = useRoute()
const router = useRouter()
const cuenta = ref<AsistenteDetalle | null>(null)
const activa = ref<AsistenteFila | null>(null)
const estado = ref<'cargando' | 'lista' | 'error' | 'no-encontrada'>('cargando')
const credenciales = ref<Credenciales | null>(null)

async function cargar() {
  const id = String(route.params.id)
  if (!cuenta.value || cuenta.value.id !== id) estado.value = 'cargando'
  try {
    // La activa se pide aparte para nombrar a ambas al reemplazarla.
    const [detalle, lista] = await Promise.all([obtenerAsistente(id), listarAsistentes()])
    cuenta.value = detalle
    activa.value = lista.find((c) => c.estado === 'activa') ?? null
    estado.value = 'lista'
  } catch (error: unknown) {
    // Un 404 no deja a la vista datos de otra cuenta.
    cuenta.value = null
    estado.value = (error as Partial<ErrorApi> | null)?.status === 404 ? 'no-encontrada' : 'error'
  }
}
onMounted(cargar)
watch(() => route.params.id, cargar)

const acciones = useAccionesAsistente({
  activaActual: () => activa.value,
  recargar: cargar,
  mostrarCredenciales: (c) => (credenciales.value = c),
  alEliminar: () => void router.push({ name: 'gerente-asistentes' }),
})
const ocupada = computed(() => !!cuenta.value && acciones.ocupada.value === cuenta.value.id)
const ETIQUETAS = { activada: 'Activada', desactivada: 'Desactivada', eliminada: 'Eliminada' }
</script>

<template>
  <div class="detalle">
    <RouterLink class="volver" :to="{ name: 'gerente-asistentes' }">
      <span class="pi pi-arrow-left" aria-hidden="true"></span>Volver a asistentes
    </RouterLink>

    <div v-if="estado === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando la cuenta…</p>
      <div class="marcador marcador--cabecera"></div>
      <div class="marcador marcador--cuerpo"></div>
    </div>

    <div v-else-if="estado === 'no-encontrada'" class="fallo" role="alert">
      <h1>Cuenta no disponible</h1>
      <p>No existe o ya no forma parte de tus asistentes.</p>
      <RouterLink class="enlace" :to="{ name: 'gerente-asistentes' }"
        >Ver tus asistentes</RouterLink
      >
    </div>

    <div v-else-if="estado === 'error' || !cuenta" class="fallo" role="alert">
      <h1>No pudimos cargar la cuenta.</h1>
      <p>Revisa tu conexión e inténtalo otra vez.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="cargar" />
    </div>

    <template v-else>
      <header class="cabecera" :class="{ 'es-activa': cuenta.estado === 'activa' }">
        <span class="monograma" aria-hidden="true">{{ iniciales(cuenta) }}</span>
        <div class="identidad">
          <h1>{{ nombreDe(cuenta) }}</h1>
          <p>
            <span class="usuario">{{ cuenta.username }}</span>
            <EtiquetaEstado :estado="cuenta.estado" />
          </p>
        </div>
        <div class="acciones">
          <Button
            v-if="cuenta.estado === 'inactiva'"
            :label="`Activar a ${cuenta.nombres || cuenta.username}`"
            :loading="ocupada"
            @click="acciones.activar(cuenta)"
          />
          <Button
            v-else
            label="Desactivar"
            severity="danger"
            outlined
            :loading="ocupada"
            @click="acciones.desactivar(cuenta)"
          />
          <Button
            label="Restablecer contraseña"
            icon="pi pi-key"
            text
            :disabled="ocupada"
            @click="acciones.restablecer(cuenta)"
          />
          <Button
            v-if="cuenta.estado === 'inactiva'"
            label="Eliminar cuenta"
            icon="pi pi-trash"
            severity="danger"
            text
            :disabled="ocupada"
            @click="acciones.eliminar(cuenta)"
          />
        </div>
      </header>

      <div class="cuerpo">
        <section aria-labelledby="datos-titulo">
          <h2 id="datos-titulo">Datos</h2>
          <dl class="datos">
            <div>
              <dt>Usuario</dt>
              <dd>{{ cuenta.username }}</dd>
            </div>
            <div>
              <dt>Estado</dt>
              <dd>
                {{
                  cuenta.estado === 'activa'
                    ? 'Activa: atiende tus pagos'
                    : 'Inactiva: no puede ingresar'
                }}
              </dd>
            </div>
            <div>
              <dt>Creada</dt>
              <dd>{{ fechaHora(cuenta.creado_en) }}</dd>
            </div>
            <div>
              <dt>Último ingreso</dt>
              <dd>{{ fechaHora(cuenta.ultimo_ingreso) }}</dd>
            </div>
          </dl>
        </section>

        <section aria-labelledby="historial-titulo">
          <h2 id="historial-titulo">Historial de activaciones</h2>
          <p v-if="!cuenta.historial.length" class="vacio">
            Todavía no hay cambios de estado registrados.
          </p>
          <ol v-else class="historial">
            <li
              v-for="(evento, i) in cuenta.historial"
              :key="`${evento.creado_en}-${i}`"
              :class="evento.accion"
            >
              <span class="hito" aria-hidden="true"></span>
              <span class="accion">{{ ETIQUETAS[evento.accion] }}</span>
              <span class="cuando">
                {{ fechaHora(evento.creado_en, '') }}, por {{ evento.realizada_por }}
              </span>
            </li>
          </ol>
        </section>
      </div>
    </template>

    <DialogoCredenciales
      v-if="credenciales"
      :credenciales="credenciales"
      motivo="restablecimiento"
      @cerrar="credenciales = null"
    />
  </div>
</template>

<style scoped>
.detalle {
  max-width: 1120px;
}
.volver {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  margin-bottom: 20px;
  color: var(--deconsta-primary);
  font-weight: 600;
  text-decoration: none;
}
.volver:hover {
  text-decoration: underline;
  text-underline-offset: 4px;
}
.volver:focus-visible,
.enlace:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 3px;
  border-radius: 2px;
}
.cabecera {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 20px 24px;
  padding-bottom: 28px;
  border-bottom: 1px solid var(--deconsta-linea);
}
.monograma {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 72px;
  height: 72px;
  border-radius: 5px 24px 5px 5px;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-family: Literata, Georgia, serif;
  font-size: 1.625rem;
  font-weight: 500;
}
.es-activa .monograma {
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.identidad {
  flex: 1 1 260px;
  min-width: 0;
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.15;
  overflow-wrap: anywhere;
}
.identidad p {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin: 10px 0 0;
}
.usuario {
  color: var(--deconsta-muted);
}
.acciones {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.acciones :deep(.p-button) {
  min-height: 44px;
}
/* Datos e historial lado a lado en escritorio, en el mismo orden de lectura y tabulación. */
.cuerpo {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 32px clamp(32px, 5vw, 72px);
  padding-top: 32px;
}
h2 {
  margin: 0 0 18px;
  font-size: var(--texto-lg);
  font-weight: 700;
  letter-spacing: -0.015em;
}
.datos {
  display: grid;
  gap: 16px;
  margin: 0;
}
.datos dt {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.datos dd {
  margin: 2px 0 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}
/* El historial es una secuencia: línea de tiempo del más reciente al más antiguo. */
.historial {
  position: relative;
  display: grid;
  gap: 22px;
  margin: 0;
  padding: 0 0 0 28px;
  list-style: none;
}
.historial::before {
  content: '';
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 6px;
  width: 2px;
  background: var(--deconsta-linea);
}
.historial li {
  position: relative;
  display: grid;
  gap: 2px;
}
.hito {
  position: absolute;
  top: 5px;
  left: -28px;
  width: 14px;
  height: 14px;
  border: 2px solid var(--deconsta-muted);
  border-radius: 50%;
  background: var(--deconsta-paper);
}
.activada .hito {
  border-color: var(--deconsta-primary);
  background: var(--deconsta-primary);
}
.eliminada .hito {
  border-color: var(--deconsta-error);
}
.accion {
  font-weight: 700;
}
.cuando {
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
.vacio {
  margin: 0;
  color: var(--deconsta-muted);
}
.fallo {
  max-width: 52ch;
  padding: 24px 28px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo h1 {
  font-size: var(--texto-lg);
}
.fallo p {
  margin: 8px 0 20px;
}
.enlace {
  color: var(--deconsta-primary);
  font-weight: 600;
  text-underline-offset: 4px;
}
.marcador {
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
.marcador--cabecera {
  height: 96px;
  margin-bottom: 28px;
}
.marcador--cuerpo {
  height: 220px;
}
@keyframes brillo {
  to {
    background-position: -200% 0;
  }
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}
@media (max-width: 760px) {
  .cuerpo {
    grid-template-columns: minmax(0, 1fr);
  }
  .acciones {
    width: 100%;
  }
  .acciones :deep(.p-button:first-child) {
    flex: 1 1 100%;
  }
}
</style>
