<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import Button from 'primevue/button'
import EtiquetaEstado from '@/components/asistentes/EtiquetaEstado.vue'
import DialogoCrearAsistente from '@/components/asistentes/DialogoCrearAsistente.vue'
import DialogoCredenciales from '@/components/asistentes/DialogoCredenciales.vue'
import { listarAsistentes } from '@/api/asistentes'
import { useAccionesAsistente } from '@/composables/useAccionesAsistente'
import {
  fechaHora,
  iniciales,
  nombreDe,
  type AsistenteFila,
  type Credenciales,
} from '@/types/asistentes'

// H03: lista de cuentas de asistente del gerente, creación y credenciales (TASK-11).
const cuentas = ref<AsistenteFila[]>([])
const estado = ref<'cargando' | 'lista' | 'error'>('cargando')
const creando = ref(false)
const credenciales = ref<(Credenciales & { motivo: 'alta' | 'restablecimiento' }) | null>(null)
const nuevaInactiva = ref<AsistenteFila | null>(null)

const activa = computed(() => cuentas.value.find((c) => c.estado === 'activa') ?? null)

async function cargar() {
  if (!cuentas.value.length) estado.value = 'cargando'
  try {
    cuentas.value = await listarAsistentes()
    estado.value = 'lista'
  } catch {
    // Con datos ya mostrados se conservan; sin ellos no se finge una lista vacía.
    if (!cuentas.value.length) estado.value = 'error'
  }
}
onMounted(cargar)

const acciones = useAccionesAsistente({
  activaActual: () => activa.value,
  recargar: cargar,
  mostrarCredenciales: (c) => (credenciales.value = { ...c, motivo: 'restablecimiento' }),
})

async function alCrear(creada: Credenciales & { estado: string }) {
  creando.value = false
  credenciales.value = { ...creada, motivo: 'alta' }
  await cargar()
  nuevaInactiva.value =
    creada.estado === 'inactiva' ? (cuentas.value.find((c) => c.id === creada.id) ?? null) : null
}

function cerrarCredenciales(activarLuego = false) {
  credenciales.value = null
  const cuenta = nuevaInactiva.value
  nuevaInactiva.value = null
  if (activarLuego && cuenta) acciones.activar(cuenta)
}
</script>

<template>
  <div class="asistentes">
    <header class="encabezado">
      <div>
        <h1>Asistentes</h1>
        <p>Gestiona quién puede atender los pagos de tu cuenta.</p>
      </div>
      <Button label="Crear asistente" icon="pi pi-plus" @click="creando = true" />
    </header>

    <div v-if="estado === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando asistentes…</p>
      <div class="marcador marcador--franja"></div>
      <div v-for="n in 3" :key="n" class="marcador marcador--fila"></div>
    </div>

    <div v-else-if="estado === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar tus asistentes.</h2>
      <p>Revisa tu conexión e inténtalo otra vez.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="cargar" />
    </div>

    <section v-else-if="!cuentas.length" class="vacio" aria-labelledby="vacio-titulo">
      <h2 id="vacio-titulo">Todavía no tienes asistentes</h2>
      <p>Crea la primera cuenta para delegar la atención de pagos.</p>
      <Button label="Crear primera asistente" icon="pi pi-plus" outlined @click="creando = true" />
    </section>

    <template v-else>
      <!-- CA02: quién atiende los pagos se lee antes que la lista. -->
      <section v-if="activa" class="turno" aria-label="Asistente activa">
        <span class="monograma" aria-hidden="true">{{ iniciales(activa) }}</span>
        <div class="turno-texto">
          <p class="turno-nombre">{{ nombreDe(activa) }} atiende tus pagos</p>
          <p class="turno-dato">Último ingreso: {{ fechaHora(activa.ultimo_ingreso) }}</p>
        </div>
        <RouterLink class="enlace" :to="{ name: 'gerente-asistente', params: { id: activa.id } }">
          Ver detalle
        </RouterLink>
      </section>
      <p v-else class="sin-turno" role="status">
        No hay una asistente activa. Tú atenderás los pagos.
      </p>

      <table class="tabla">
        <caption class="lector">
          Cuentas de asistente
        </caption>
        <thead>
          <tr>
            <th scope="col">Nombre</th>
            <th scope="col">Estado</th>
            <th scope="col">Último ingreso</th>
            <th scope="col"><span class="lector">Acciones</span></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="cuenta in cuentas"
            :key="cuenta.id"
            :class="{ 'es-activa': cuenta.estado === 'activa' }"
          >
            <th scope="row">
              <span class="quien">
                <span class="monograma monograma--chico" aria-hidden="true">{{
                  iniciales(cuenta)
                }}</span>
                <span>
                  <span class="nombre">{{ nombreDe(cuenta) }}</span>
                  <span class="usuario">{{ cuenta.username }}</span>
                </span>
              </span>
            </th>
            <td data-campo="Estado"><EtiquetaEstado :estado="cuenta.estado" /></td>
            <td data-campo="Último ingreso">{{ fechaHora(cuenta.ultimo_ingreso) }}</td>
            <td class="acciones">
              <Button
                v-if="cuenta.estado === 'inactiva'"
                label="Activar"
                size="small"
                outlined
                :loading="acciones.ocupada.value === cuenta.id"
                :aria-label="`Activar a ${nombreDe(cuenta)}`"
                @click="acciones.activar(cuenta)"
              />
              <RouterLink
                class="enlace"
                :to="{ name: 'gerente-asistente', params: { id: cuenta.id } }"
                :aria-label="`Ver detalle de ${nombreDe(cuenta)}`"
              >
                Ver detalle
              </RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <DialogoCrearAsistente
      v-if="creando"
      :activa="activa ? nombreDe(activa) : null"
      @creada="alCrear"
      @cerrar="creando = false"
    />
    <DialogoCredenciales
      v-if="credenciales"
      :credenciales="credenciales"
      :motivo="credenciales.motivo"
      :ofrecer-activar="!!nuevaInactiva"
      @cerrar="cerrarCredenciales()"
      @activar="cerrarCredenciales(true)"
    />
  </div>
</template>

<style scoped>
.asistentes {
  max-width: 1120px;
}
.encabezado {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px 32px;
  margin-bottom: clamp(28px, 4vw, 40px);
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
  margin: 10px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
.encabezado :deep(.p-button) {
  min-height: 44px;
}
/* La franja de turno usa la esquina de la marca: es la credencial de quien atiende hoy. */
.turno {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 20px;
  margin-bottom: 28px;
  padding: 18px 22px;
  border-radius: 5px 28px 5px 5px;
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.turno .monograma {
  background: var(--deconsta-paper);
  color: var(--deconsta-primary);
}
.turno-texto {
  flex: 1 1 220px;
  min-width: 0;
}
.turno-nombre {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.turno-dato {
  margin: 2px 0 0;
  color: var(--deconsta-sobre-mesa);
  font-size: var(--texto-sm);
}
.turno .enlace {
  color: var(--deconsta-paper);
}
.sin-turno {
  margin: 0 0 28px;
  padding: 14px 18px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  font-weight: 600;
}
.monograma {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 4px 16px 4px 4px;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-family: Literata, Georgia, serif;
  font-size: 1.125rem;
  font-weight: 600;
}
.monograma--chico {
  width: 38px;
  height: 38px;
  border-radius: 4px 13px 4px 4px;
  font-size: 0.9375rem;
}
.tabla {
  width: 100%;
  border-collapse: collapse;
}
thead th {
  padding: 0 16px 10px;
  border-bottom: 1px solid var(--deconsta-linea);
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  font-weight: 600;
  text-align: left;
}
tbody th,
tbody td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--deconsta-linea);
  text-align: left;
  vertical-align: middle;
}
tbody th {
  font-weight: inherit;
}
/* CA02: la activa se distingue con franja y rótulo, no solo con color. */
tbody tr.es-activa {
  background: var(--deconsta-paper-claro);
  box-shadow: inset 4px 0 0 var(--deconsta-primary);
}
.quien {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.nombre {
  display: block;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.usuario {
  display: block;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
  overflow-wrap: anywhere;
}
.acciones {
  white-space: nowrap;
  text-align: right;
}
.acciones :deep(.p-button) {
  margin-right: 12px;
  min-height: 36px;
}
.enlace {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  color: var(--deconsta-primary);
  font-weight: 600;
  text-underline-offset: 4px;
}
.enlace:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 3px;
  border-radius: 2px;
}
.vacio {
  max-width: 52ch;
  padding: clamp(28px, 5vw, 48px) 0;
}
.vacio h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.vacio p {
  margin: 8px 0 24px;
  color: var(--deconsta-muted);
  line-height: 1.6;
}
.fallo {
  max-width: 52ch;
  padding: 24px 28px;
  border-left: 3px solid var(--deconsta-error);
  background: var(--deconsta-error-fondo);
}
.fallo h2 {
  margin: 0;
  font-size: var(--texto-lg);
}
.fallo p {
  margin: 8px 0 20px;
}
.marcador {
  border-radius: var(--radio-control);
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
}
.marcador--franja {
  height: 84px;
  margin-bottom: 28px;
}
.marcador--fila {
  height: 64px;
  margin-bottom: 8px;
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
  white-space: nowrap;
}
/* En celular cada fila es una tarjeta con sus cuatro datos; no hay tabla horizontal. */
@media (max-width: 720px) {
  .encabezado :deep(.p-button) {
    width: 100%;
  }
  .turno {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 4px 14px;
    padding: 16px 18px;
    border-radius: 5px 20px 5px 5px;
  }
  .turno .monograma {
    width: 40px;
    height: 40px;
  }
  .turno-nombre {
    font-size: var(--texto-md);
  }
  .turno .enlace {
    grid-column: 2;
    min-height: 36px;
  }
  thead {
    display: none;
  }
  .tabla,
  tbody,
  tr,
  tbody th,
  tbody td {
    display: block;
  }
  tbody tr {
    margin-bottom: 12px;
    padding: 6px 16px;
    border: 1px solid var(--deconsta-linea);
    border-radius: 5px 18px 5px 5px;
    background: var(--deconsta-paper-claro);
  }
  tbody th,
  tbody td {
    padding: 10px 0;
    border-bottom: 0;
  }
  tbody td[data-campo] {
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }
  tbody td[data-campo]::before {
    content: attr(data-campo);
    color: var(--deconsta-muted);
    font-size: var(--texto-sm);
  }
  .acciones {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid var(--deconsta-linea);
  }
}
</style>
