<script setup lang="ts">
import { computed } from 'vue'
import Button from 'primevue/button'
import GrupoRuta from './GrupoRuta.vue'
import { avance, textoTotal, type ResultadoDeuda, type Ruta } from './modelo'

// H23: los pagos presenciales agrupados por lugar para hacerlos en una sola salida (CA01). Se
// eligen las deudas con el total a llevar (CA02), cada una se marca pagada al avanzar (CA03) y al
// terminar se recuerda subir los comprobantes (CA04). Quien la usa trae los datos (TASK-80).
const props = withDefaults(
  defineProps<{
    ruta?: Ruta | null
    estadoPantalla?: 'lista' | 'cargando' | 'error'
    hoy: string
    seleccion?: string[]
    ocupado?: string | null
    iniciando?: boolean
    /** Lo que respondió el último inicio en lote; se muestra lo que no se inició. */
    resultados?: ResultadoDeuda[] | null
  }>(),
  {
    ruta: null,
    estadoPantalla: 'lista',
    seleccion: () => [],
    ocupado: null,
    iniciando: false,
    resultados: null,
  },
)
const emit = defineEmits<{
  seleccionar: [ids: string[]]
  iniciar: []
  marcar: [id: string]
  adjuntar: [id: string]
  abrir: [id: string]
  reintentar: []
  cerrarResultados: []
  irBandeja: []
}>()

const grupos = computed(() => props.ruta?.grupos ?? [])
const items = computed(() => grupos.value.flatMap((g) => g.items))
const elegidas = computed(() => items.value.filter((i) => props.seleccion.includes(i.id)))
const progreso = computed(() => avance(grupos.value))
const nombre = (id: string) => {
  const item = items.value.find((i) => i.id === id)
  return item ? item.alias || item.empresa || 'Servicio' : 'Una deuda'
}
const sinIniciar = computed(() =>
  (props.resultados ?? []).filter((r) => r.resultado !== 'iniciada'),
)
const iniciadas = computed(
  () => (props.resultados ?? []).filter((r) => r.resultado === 'iniciada').length,
)
</script>

<template>
  <section class="ruta" aria-labelledby="ruta-titulo">
    <header class="encabezado">
      <h1 id="ruta-titulo">Ruta de pagos</h1>
      <p>
        Agrupa los pagos presenciales por lugar para hacerlos en una sola salida. Banca móvil y Yape
        no aparecen aquí.
      </p>
    </header>

    <div v-if="estadoPantalla === 'cargando'" aria-busy="true">
      <p class="lector" role="status">Cargando la ruta…</p>
      <div v-for="n in 3" :key="n" class="marcador"></div>
    </div>

    <div v-else-if="estadoPantalla === 'error'" class="fallo" role="alert">
      <h2>No pudimos cargar la ruta.</h2>
      <p>Revisa tu conexión e inténtalo otra vez.</p>
      <Button label="Reintentar" icon="pi pi-refresh" @click="emit('reintentar')" />
    </div>

    <template v-else>
      <div
        v-if="resultados && resultados.length"
        class="resultado"
        :class="{ todo: !sinIniciar.length }"
        role="status"
      >
        <div>
          <p class="resultado-titulo">
            <template v-if="iniciadas">
              {{ iniciadas === 1 ? 'Iniciaste 1 pago' : `Iniciaste ${iniciadas} pagos` }}.
            </template>
            <template v-if="sinIniciar.length">
              {{
                sinIniciar.length === 1
                  ? '1 deuda no se inició:'
                  : `${sinIniciar.length} deudas no se iniciaron:`
              }}
            </template>
          </p>
          <ul v-if="sinIniciar.length">
            <li v-for="r in sinIniciar" :key="r.deuda_id">
              <strong>{{ nombre(r.deuda_id) }}</strong> ·
              {{
                r.resultado === 'requiere_aprobacion'
                  ? 'necesita la aprobación del gerente; ya se la pedimos.'
                  : r.mensaje
              }}
            </li>
          </ul>
        </div>
        <Button
          icon="pi pi-times"
          text
          rounded
          aria-label="Cerrar el resultado"
          @click="emit('cerrarResultados')"
        />
      </div>

      <div v-if="progreso.terminada" class="aviso-fin" role="status">
        <span class="aviso-icono" aria-hidden="true"><i class="pi pi-flag-fill"></i></span>
        <div>
          <h2>Terminaste la ruta</h2>
          <p v-if="progreso.sinComprobante.length">
            Sube el comprobante de cada pago para que se valide:
            {{
              progreso.sinComprobante.length === 1
                ? 'falta 1'
                : `faltan ${progreso.sinComprobante.length}`
            }}.
          </p>
          <p v-else>Todos tus comprobantes se están validando.</p>
        </div>
        <Button label="Ir a la bandeja" text icon="pi pi-inbox" @click="emit('irBandeja')" />
      </div>
      <p v-else-if="progreso.enRuta.length" class="en-camino">
        <i class="pi pi-directions" aria-hidden="true"></i>
        En camino:
        <strong>
          {{ progreso.enRuta.length - progreso.porPagar.length }} de {{ progreso.enRuta.length }}
          pagadas
        </strong>
        · te falta pagar {{ textoTotal(progreso.porPagar) }}
      </p>

      <section v-if="!grupos.length" class="vacio" aria-live="polite">
        <span class="vacio-icono" aria-hidden="true"><i class="pi pi-map"></i></span>
        <h2>No hay pagos presenciales pendientes</h2>
        <p>Las deudas que se pagan por banca móvil o Yape no entran en la ruta.</p>
      </section>

      <div v-else class="grupos">
        <GrupoRuta
          v-for="grupo in grupos"
          :key="grupo.lugar ?? 'ninguno'"
          :grupo="grupo"
          :hoy="hoy"
          :seleccion="seleccion"
          :ocupado="ocupado"
          @seleccionar="emit('seleccionar', $event)"
          @marcar="emit('marcar', $event)"
          @adjuntar="emit('adjuntar', $event)"
          @abrir="emit('abrir', $event)"
        />
      </div>

      <div v-if="seleccion.length" class="seleccion" role="region" aria-label="Deudas elegidas">
        <p>
          <strong>{{ seleccion.length === 1 ? '1 deuda' : `${seleccion.length} deudas` }}</strong>
          · llevar <strong>{{ textoTotal(elegidas) }}</strong>
        </p>
        <div class="seleccion-acciones">
          <Button label="Quitar" text size="small" @click="emit('seleccionar', [])" />
          <Button
            label="Iniciar ruta"
            icon="pi pi-directions"
            :loading="iniciando"
            @click="emit('iniciar')"
          />
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.ruta {
  max-width: 880px;
}
.encabezado {
  margin-bottom: 22px;
}
h1 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-xl);
  font-weight: 500;
  letter-spacing: -0.02em;
}
.encabezado p {
  max-width: 60ch;
  margin: 8px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-md);
}
.grupos {
  display: grid;
  gap: 16px;
}
.resultado {
  display: flex;
  align-items: start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 14px 12px 18px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
}
.resultado.todo {
  border-left-color: var(--deconsta-primary);
  background: var(--deconsta-realce);
}
.resultado-titulo {
  margin: 4px 0 0;
  font-weight: 700;
}
.resultado ul {
  margin: 6px 0 4px;
  padding-left: 18px;
}
.aviso-fin {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
  margin-bottom: 18px;
  padding: 16px 18px;
  border-radius: 6px 18px 6px 6px;
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.aviso-fin > div {
  flex: 1;
  min-width: 220px;
}
.aviso-fin h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.aviso-fin p {
  margin: 4px 0 0;
  color: var(--deconsta-sobre-mesa);
}
.aviso-fin :deep(.p-button-text) {
  color: var(--deconsta-paper);
}
.aviso-icono {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: rgb(255 255 255 / 0.14);
}
.en-camino {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin: 0 0 16px;
  padding: 10px 14px;
  border-radius: var(--radio-control);
  background: var(--deconsta-realce);
  font-variant-numeric: tabular-nums;
}
.en-camino .pi {
  color: var(--deconsta-primary);
}
.seleccion {
  position: sticky;
  bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px 16px;
  margin-top: 18px;
  padding: 12px 16px 12px 20px;
  border-radius: 6px 18px 6px 6px;
  background: var(--deconsta-ink);
  box-shadow: 0 10px 30px rgb(25 44 41 / 0.25);
  color: var(--deconsta-paper);
}
.seleccion p {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.seleccion-acciones {
  display: flex;
  gap: 6px;
}
.seleccion :deep(.p-button-text) {
  color: var(--deconsta-sobre-mesa);
}
.vacio {
  padding: clamp(32px, 6vw, 64px) 0;
  text-align: center;
}
.vacio-icono {
  display: inline-grid;
  place-items: center;
  width: 64px;
  height: 64px;
  margin-bottom: 14px;
  border-radius: 50%;
  background: var(--deconsta-realce);
  color: var(--deconsta-primary);
  font-size: 1.6rem;
}
.vacio h2 {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
}
.vacio p {
  margin: 8px 0 0;
  color: var(--deconsta-muted);
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
  height: 160px;
  margin-bottom: 14px;
  border-radius: 6px 18px 6px 6px;
  background: linear-gradient(90deg, #e6ece9 0%, #f4f7f5 50%, #e6ece9 100%) 0 0 / 200% 100%;
  animation: brillo 1.4s ease-in-out infinite;
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
</style>
