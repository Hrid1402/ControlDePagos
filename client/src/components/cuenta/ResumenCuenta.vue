<script setup lang="ts">
import { computed } from 'vue'
import type { PerfilCuenta, SenalesCuenta } from '@/types/cuenta'

const props = defineProps<{ perfil: PerfilCuenta; senales: SenalesCuenta }>()

const nombreCompleto = computed(() =>
  [props.perfil.nombres, props.perfil.apellidos].filter(Boolean).join(' '),
)
const iniciales = computed(() => {
  const partes = [props.perfil.nombres, props.perfil.apellidos]
    .map((p) => p?.trim()[0])
    .filter(Boolean)
  return (partes.length ? partes.join('') : props.perfil.username[0] || '').toLocaleUpperCase('es')
})
const faltantes = computed(
  () =>
    [
      props.perfil.nombres,
      props.perfil.apellidos,
      props.perfil.correo,
      props.perfil.celular,
    ].filter((dato) => !dato).length,
)
const cambios = computed(() => {
  const restantes = props.senales.cambiosRestantes
  if (restantes === null) return 'Por confirmar'
  if (restantes === 0) return 'Sin cambios este mes'
  return restantes === 1 ? 'Queda 1 este mes' : `Quedan ${restantes} este mes`
})
</script>

<template>
  <aside class="resumen" aria-label="Resumen de tu cuenta">
    <div class="identidad">
      <span class="monograma" aria-hidden="true">{{ iniciales }}</span>
      <div>
        <p class="nombre">{{ nombreCompleto || perfil.username }}</p>
        <p class="rol">{{ perfil.rol === 'gerente' ? 'Gerente' : 'Asistente' }}</p>
      </div>
    </div>
    <dl>
      <div>
        <dt>Usuario</dt>
        <dd>{{ perfil.username }}</dd>
      </div>
      <div>
        <dt>Cambios de usuario</dt>
        <dd>{{ cambios }}</dd>
      </div>
      <div>
        <dt>Datos personales</dt>
        <dd :class="{ pendiente: faltantes }">
          {{
            faltantes
              ? `Falta${faltantes === 1 ? '' : 'n'} ${faltantes} por completar`
              : 'Completos'
          }}
        </dd>
      </div>
    </dl>
    <p v-if="senales.contrasenaInicial" class="sugerencia">
      Aún usas la contraseña inicial. Te recomendamos
      <a href="#contrasena">cambiarla</a>.
    </p>
    <nav class="indice" aria-label="En esta página">
      <a href="#datos">Datos personales</a>
      <a href="#usuario">Usuario</a>
      <a href="#contrasena">Contraseña</a>
    </nav>
  </aside>
</template>

<style scoped>
.resumen {
  display: grid;
  gap: 28px;
}
.identidad {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}
.monograma {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 64px;
  height: 64px;
  border-radius: 5px 22px 5px 5px;
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
  font-family: Literata, Georgia, serif;
  font-size: 1.5rem;
  font-weight: 500;
}
.nombre {
  margin: 0;
  font-family: Literata, Georgia, serif;
  font-size: var(--texto-lg);
  font-weight: 500;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.rol {
  margin: 4px 0 0;
  color: var(--deconsta-muted);
  font-size: var(--texto-sm);
}
dl {
  display: grid;
  gap: 14px;
  margin: 0;
  padding: 20px 0;
  border-block: 1px solid var(--deconsta-linea);
}
dl > div {
  display: grid;
  gap: 2px;
}
dt {
  color: var(--deconsta-muted);
  font-size: var(--texto-xs);
}
dd {
  margin: 0;
  font-weight: 600;
  overflow-wrap: anywhere;
}
dd.pendiente {
  color: var(--deconsta-aviso);
}
.sugerencia {
  margin: 0;
  padding: 14px 16px;
  border-left: 3px solid var(--deconsta-aviso);
  background: var(--deconsta-aviso-fondo);
  font-size: var(--texto-sm);
  line-height: 1.6;
}
.sugerencia a {
  color: inherit;
  font-weight: 700;
  text-underline-offset: 3px;
}
.indice {
  display: grid;
  gap: 2px;
}
.indice a {
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 0 12px;
  border-radius: var(--radio-control);
  color: var(--deconsta-ink);
  font-weight: 600;
  text-decoration: none;
}
.indice a:hover {
  background: var(--deconsta-realce);
}
a:focus-visible {
  outline: 2px solid var(--deconsta-primary);
  outline-offset: 2px;
}
@media (max-width: 959px) {
  .resumen {
    gap: 20px;
  }
  dl {
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 14px 24px;
  }
  .indice {
    display: none;
  }
}
</style>
