<script setup lang="ts">
import FormularioBase from '@/components/formularios/FormularioBase.vue'
import CampoTexto from '@/components/formularios/CampoTexto.vue'
import { LARGO_MINIMO_CONTRASENA, requisitosContrasena } from '@/config/reglas'
import { esquemaCambioContrasena } from '@/types/cuenta'

defineProps<{ guardar: (valores: Record<string, unknown>) => Promise<unknown> }>()

const NIVELES = ['Débil', 'Débil', 'Débil', 'Media', 'Media', 'Fuerte']
function evaluar(valor: unknown) {
  const texto = typeof valor === 'string' ? valor : ''
  const requisitos = requisitosContrasena.map((r) => ({
    etiqueta: r.etiqueta,
    cumple: r.cumple(texto),
  }))
  const cumplidos = requisitos.filter((r) => r.cumple).length
  // La fortaleza orienta y no reemplaza los requisitos (H02 CA13 y CA14): sin cumplirlos todos
  // no pasa de Media, y solo es Fuerte si además es más larga que el mínimo.
  const larga = [...texto].length >= LARGO_MINIMO_CONTRASENA + 4
  const puntos = cumplidos < requisitos.length ? Math.min(cumplidos, 3) : larga ? 5 : 4
  return { requisitos, puntos, nivel: texto ? NIVELES[puntos] : null }
}
</script>

<template>
  <section id="contrasena" class="seccion-cuenta" aria-labelledby="contrasena-titulo">
    <header>
      <h2 id="contrasena-titulo">Contraseña</h2>
      <p>Al cambiarla cerraremos tus otras sesiones; esta seguirá abierta.</p>
    </header>
    <FormularioBase
      :esquema="esquemaCambioContrasena"
      :valores-iniciales="{ contrasena_actual: '', contrasena_nueva: '', confirmacion: '' }"
      :guardar="guardar"
      texto-boton="Cambiar contraseña"
      mensaje-exito="Contraseña cambiada. Cerramos tus demás sesiones."
      limpiar-al-guardar
    >
      <template #default="{ valores }">
        <div class="composicion">
          <div class="actual">
            <CampoTexto
              nombre="contrasena_actual"
              etiqueta="Contraseña actual"
              tipo="password"
              autocomplete="current-password"
            />
          </div>
          <div class="nueva">
            <CampoTexto
              nombre="contrasena_nueva"
              etiqueta="Nueva contraseña"
              tipo="password"
              autocomplete="new-password"
            />
          </div>
          <div class="confirmacion">
            <CampoTexto
              nombre="confirmacion"
              etiqueta="Confirma la nueva contraseña"
              tipo="password"
              autocomplete="new-password"
            />
          </div>
          <div class="requisitos">
            <p class="titulo-requisitos">La nueva contraseña necesita</p>
            <ul>
              <li
                v-for="requisito in evaluar(valores.contrasena_nueva).requisitos"
                :key="requisito.etiqueta"
                :class="{ cumple: requisito.cumple }"
              >
                <span class="marca" aria-hidden="true"></span>
                {{ requisito.etiqueta }}
                <span class="lector">{{ requisito.cumple ? ': cumple' : ': falta' }}</span>
              </li>
            </ul>
            <div
              class="medidor"
              :data-puntos="evaluar(valores.contrasena_nueva).puntos"
              aria-hidden="true"
            >
              <span
                v-for="n in 5"
                :key="n"
                :class="{ lleno: n <= evaluar(valores.contrasena_nueva).puntos }"
              ></span>
            </div>
            <p class="nivel" aria-live="polite">
              <template v-if="evaluar(valores.contrasena_nueva).nivel">
                Seguridad: <strong>{{ evaluar(valores.contrasena_nueva).nivel }}</strong>
              </template>
              <template v-else>Escríbela para ver su seguridad.</template>
            </p>
          </div>
        </div>
      </template>
    </FormularioBase>
  </section>
</template>

<style scoped>
/* Los requisitos acompañan a los tres campos en escritorio; en celular van justo bajo la
   nueva contraseña, que es donde se miran mientras se escribe. */
.composicion {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(200px, 240px);
  grid-template-areas:
    'actual requisitos'
    'nueva requisitos'
    'confirmacion requisitos';
  gap: 24px 40px;
  align-items: start;
}
.actual {
  grid-area: actual;
}
.nueva {
  grid-area: nueva;
}
.confirmacion {
  grid-area: confirmacion;
}
.requisitos {
  grid-area: requisitos;
  padding: 20px;
  border-radius: 4px 18px 4px 4px;
  background: var(--deconsta-paper-claro);
  font-size: var(--texto-sm);
}
.titulo-requisitos {
  margin: 0 0 12px;
  font-weight: 600;
}
ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--deconsta-muted);
}
li {
  display: flex;
  align-items: center;
  gap: 10px;
}
.marca {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  border: 1.5px solid var(--deconsta-muted);
  border-radius: 50%;
}
li.cumple {
  color: var(--deconsta-primary);
  font-weight: 600;
}
li.cumple .marca {
  border-color: var(--deconsta-primary);
  background:
    no-repeat center / 9px
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 8'%3E%3Cpath d='M1 4l3 3 5-6' fill='none' stroke='white' stroke-width='1.6'/%3E%3C/svg%3E"),
    var(--deconsta-primary);
}
.medidor {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
  margin-top: 18px;
}
.medidor span {
  height: 4px;
  border-radius: 2px;
  background: var(--deconsta-linea);
  transition: background-color 0.2s ease;
}
.medidor span.lleno {
  background: var(--deconsta-error);
}
.medidor[data-puntos='3'] span.lleno,
.medidor[data-puntos='4'] span.lleno {
  background: var(--deconsta-aviso);
}
.medidor[data-puntos='5'] span.lleno {
  background: var(--deconsta-primary);
}
.nivel {
  margin: 10px 0 0;
  color: var(--deconsta-muted);
}
.nivel strong {
  color: var(--deconsta-ink);
}
.lector {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
@media (max-width: 760px) {
  .composicion {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'actual' 'nueva' 'requisitos' 'confirmacion';
  }
}
</style>
