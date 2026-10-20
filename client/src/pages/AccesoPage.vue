<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarcoAcceso from '@/components/acceso/MarcoAcceso.vue'
import FormularioIngreso from '@/components/acceso/FormularioIngreso.vue'
import FormularioRecuperacion from '@/components/acceso/FormularioRecuperacion.vue'
import FormularioClave from '@/components/acceso/FormularioClave.vue'
import { controlSesionKey } from '@/services/controlSesion'
import { retornoAutorizado } from '@/router/guard'
import type { EstadoIngreso, PantallaAcceso } from '@/types/acceso'
import '@/assets/acceso.css'
const route = useRoute()
const router = useRouter()
const control = inject(controlSesionKey, null)
const comprobando = ref(false)
const disponibilidad = ref('')
const revision = ref<HTMLDetailsElement>()
const raiz = ref<HTMLDivElement>()
const revisando = computed(() => import.meta.env.DEV && route.query.revision === '1')
const pantallas: { valor: PantallaAcceso; nombre: string }[] = [
  { valor: 'ingreso', nombre: 'Acceso' },
  { valor: 'recuperar', nombre: 'Recuperación' },
  { valor: 'correo-enviado', nombre: 'Correo enviado' },
  { valor: 'restablecer', nombre: 'Nueva contraseña' },
  { valor: 'clave-actualizada', nombre: 'Contraseña actualizada' },
  { valor: 'enlace-invalido', nombre: 'Enlace vencido o usado' },
  { valor: 'sin-permiso', nombre: 'Sin acceso' },
]
const pantalla = computed<PantallaAcceso | 'no-encontrada'>(() => {
  if (revisando.value)
    return pantallas.find((p) => p.valor === route.query.pantalla)?.valor || 'ingreso'
  return (
    (
      {
        recuperar: 'recuperar',
        restablecer: 'restablecer',
        'sin-permiso': 'sin-permiso',
        'no-encontrada': 'no-encontrada',
      } as const
    )[route.name as string] || 'ingreso'
  )
})
const estado = ref<EstadoIngreso>('normal')
const motivos: Record<string, string> = {
  inactividad: 'Cerramos tu sesión tras 30 minutos sin actividad.',
  SESION_REVOCADA: 'Tu sesión fue revocada. Tendrás que iniciar sesión de nuevo.',
  CUENTA_INACTIVA: 'Tu cuenta ya no está activa. Contacta con tu gerente.',
  NO_AUTENTICADO: 'Tu sesión venció. Tendrás que iniciar sesión de nuevo.',
  'otra-pestana': 'La sesión se cerró desde otra pestaña.',
  'sin-conexion': 'No pudimos comprobar tu sesión. Revisa tu conexión y vuelve a intentar.',
}
const aviso = computed(
  () =>
    disponibilidad.value ||
    motivos[String(route.query.motivo)] ||
    (revisando.value
      ? {
          normal: '',
          vacio: '',
          cargando: '',
          incorrecto:
            'El usuario o la contraseña no son correctos. Revisa tus datos e intenta de nuevo.',
          bloqueado:
            'Tu cuenta está bloqueada por varios intentos fallidos. Podrás volver a intentarlo en 15 minutos.',
          inactiva: 'Tu cuenta está inactiva. Contacta con quien te entregó el acceso.',
          'sin-conexion':
            'No pudimos conectar. Lo que escribiste sigue aquí; revisa tu conexión y vuelve a intentar.',
          vencida: 'Tu sesión terminó. Vuelve a ingresar para continuar donde estabas.',
        }[estado.value]
      : ''),
)
const errorIngreso = computed(
  () => revisando.value && ['incorrecto', 'bloqueado', 'inactiva'].includes(estado.value),
)
const mensaje = computed(
  () =>
    ({
      'correo-enviado': {
        titulo: 'Revisa tu correo.',
        texto:
          'Si el correo está registrado, recibirás un enlace para cambiar tu contraseña. Revisa también el correo no deseado.',
        accion: 'Volver al acceso',
        destino: 'ingreso' as const,
      },
      'clave-actualizada': {
        titulo: 'Tu próxima entrada ya tiene otra clave.',
        texto: 'La contraseña se actualizó. Inicia sesión con la nueva para volver a tu espacio.',
        accion: 'Ir al acceso',
        destino: 'ingreso' as const,
      },
      'enlace-invalido': {
        titulo: 'Necesitas un nuevo enlace.',
        texto:
          'Este enlace venció o ya fue utilizado. Puedes solicitar otro para recuperar el acceso.',
        accion: 'Solicitar otro enlace',
        destino: 'recuperar' as const,
      },
      'sin-permiso': {
        titulo: 'Este espacio no es el tuyo.',
        texto:
          'Tu cuenta no tiene permiso para abrir esta página. Puedes volver al espacio que te corresponde.',
        accion: control?.sesion.rol ? 'Volver a mi espacio' : 'Volver al acceso',
        destino: 'ingreso' as const,
      },
      'no-encontrada': {
        titulo: 'No encontramos esa página.',
        texto: 'Esta dirección no está disponible.',
        accion: 'Volver al inicio',
        destino: 'ingreso' as const,
      },
    })[
      pantalla.value as
        'correo-enviado' | 'clave-actualizada' | 'enlace-invalido' | 'sin-permiso' | 'no-encontrada'
    ],
)
function ir(destino: PantallaAcceso) {
  if (revisando.value)
    void router.push({ name: 'login', query: { revision: '1', pantalla: destino } })
  else void router.push({ name: destino === 'ingreso' ? 'login' : destino })
}
function pendiente() {
  disponibilidad.value = 'Esta opción estará disponible pronto.'
}
function volver() {
  if (pantalla.value === 'sin-permiso' && control?.sesion.rol) {
    void router.push(retornoAutorizado(router, undefined, control.sesion.rol))
  } else if (mensaje.value) ir(mensaje.value.destino)
}
async function reintentar() {
  if (!control || comprobando.value) return
  comprobando.value = true
  try {
    if ((await control.verificar(true)) && control.sesion.rol)
      await router.replace(retornoAutorizado(router, route.query.redirect, control.sesion.rol))
  } catch {
    /* Se conserva el aviso y la opción de reintentar. */
  } finally {
    comprobando.value = false
  }
}
watch(pantalla, async () => {
  disponibilidad.value = ''
  estado.value = 'normal'
  if (revision.value) revision.value.open = false
  await nextTick()
  raiz.value?.querySelector<HTMLElement>('#contenido-acceso')?.focus({ preventScroll: true })
  window.scrollTo({ top: 0 })
})
</script>
<template>
  <div ref="raiz" class="pagina-acceso">
    <MarcoAcceso :compacto="pantalla === 'ingreso'" @inicio="ir('ingreso')">
      <div v-if="pantalla === 'ingreso'" class="composicion-ingreso">
        <section class="hero-ingreso">
          <h1>Todo en <span>su lugar.</span></h1>
          <img
            src="/brand/deconsta/logo/deconsta-symbol-white.svg"
            alt=""
            width="380"
            height="380"
          />
        </section>
        <FormularioIngreso
          :cargando="comprobando || (revisando && estado === 'cargando')"
          :bloqueado="revisando && (estado === 'bloqueado' || estado === 'inactiva')"
          :mostrar-vacios="revisando && estado === 'vacio'"
          @enviar="pendiente"
          @recuperar="ir('recuperar')"
        >
          <template #aviso
            ><div
              v-if="aviso"
              class="aviso-acceso"
              :class="{ 'aviso-acceso--error': errorIngreso }"
              :role="errorIngreso ? 'alert' : 'status'"
            >
              {{ aviso }}
              <button
                v-if="control?.sesion.token"
                class="enlace-acceso"
                type="button"
                :disabled="comprobando"
                @click="reintentar"
              >
                Reintentar
              </button>
            </div></template
          >
        </FormularioIngreso>
      </div>
      <template v-else-if="pantalla === 'recuperar'">
        <section class="hero-secundario">
          <h1>Volvamos a tu espacio.</h1>
          <p>Te enviaremos un enlace para elegir una nueva contraseña.</p>
        </section>
        <FormularioRecuperacion @enviar="pendiente" @volver="ir('ingreso')" />
      </template>
      <template v-else-if="pantalla === 'restablecer'">
        <section class="hero-secundario">
          <h1>Una nueva contraseña. El mismo espacio.</h1>
          <p>Elige una distinta de la actual y de tus últimas tres contraseñas.</p>
        </section>
        <FormularioClave @enviar="pendiente" @volver="ir('ingreso')" />
      </template>
      <section v-else-if="mensaje" class="mensaje-diseno">
        <h1>{{ mensaje.titulo }}</h1>
        <p>{{ mensaje.texto }}</p>
        <div>
          <button type="button" class="boton-acceso boton-acceso--claro" @click="volver">
            {{ mensaje.accion }}</button
          ><button
            v-if="pantalla === 'correo-enviado'"
            type="button"
            class="enlace-acceso"
            @click="ir('recuperar')"
          >
            Usar otro correo</button
          ><button
            v-else-if="pantalla === 'sin-permiso' && control?.sesion.token"
            type="button"
            class="enlace-acceso"
            @click="control?.sesion.cerrar()"
          >
            Cerrar sesión
          </button>
        </div>
      </section>
      <p v-if="disponibilidad && pantalla !== 'ingreso'" class="aviso-acceso" role="status">
        {{ disponibilidad }}
      </p>
      <template v-if="revisando" #pie>
        <details ref="revision" class="selector-revision">
          <summary>Revisar diseño Vue</summary>
          <div class="panel-revision">
            <p>Solo revisión visual. Las acciones no acceden a cuentas reales ni guardan datos.</p>
            <label for="pantalla-revision">Pantalla</label
            ><select
              id="pantalla-revision"
              :value="pantalla"
              @change="ir(($event.target as HTMLSelectElement).value as PantallaAcceso)"
            >
              <option v-for="opcion in pantallas" :key="opcion.valor" :value="opcion.valor">
                {{ opcion.nombre }}
              </option></select
            ><template v-if="pantalla === 'ingreso'"
              ><label for="estado-revision">Estado del acceso</label
              ><select id="estado-revision" v-model="estado">
                <option value="normal">Normal</option>
                <option value="vacio">Campos vacíos</option>
                <option value="incorrecto">Credenciales incorrectas</option>
                <option value="bloqueado">Cuenta bloqueada</option>
                <option value="inactiva">Cuenta inactiva</option>
                <option value="sin-conexion">Sin conexión</option>
                <option value="cargando">Cargando</option>
                <option value="vencida">Sesión vencida</option>
              </select></template
            >
          </div>
        </details>
      </template>
    </MarcoAcceso>
  </div>
</template>
<style scoped>
.composicion-ingreso {
  display: flex;
  flex-direction: column;
  gap: clamp(16px, 3vh, 30px);
  flex: 1;
  min-height: 0;
}
.hero-ingreso {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  align-items: center;
  gap: 40px;
  flex: 1;
  min-height: 0;
  padding: 4px 24px;
}
.hero-ingreso h1 {
  font-size: clamp(52px, min(7.8vw, 11svh), 112px);
}
.hero-ingreso h1 span {
  display: block;
}
.hero-ingreso img {
  width: min(100%, 36svh, 380px);
  height: auto;
  justify-self: center;
  opacity: 0.8;
  transform: rotate(-8deg);
}
.hero-secundario {
  display: flex;
  flex-direction: column;
  justify-content: center;
  flex: 1;
  gap: 24px;
  padding: 30px 24px;
  min-height: 240px;
}
.hero-secundario h1,
.mensaje-diseno h1 {
  font-size: clamp(44px, 5.5vw, 78px);
  max-width: 15ch;
}
.hero-secundario p,
.mensaje-diseno > p {
  color: #d4e4da;
  font-size: 17px;
  line-height: 1.75;
  max-width: 48ch;
}
.mensaje-diseno {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 30px;
  padding: 40px 24px;
}
.mensaje-diseno > div {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  align-items: center;
}
.selector-revision {
  position: relative;
  z-index: 30;
  color: #192c29;
  flex-shrink: 0;
  font-size: 12px;
}
.selector-revision summary {
  border: 1px solid #a9bfb0;
  background: white;
  border-radius: 7px;
  padding: 10px 14px;
  min-height: 40px;
  display: flex;
  align-items: center;
  cursor: pointer;
  list-style: none;
}
.selector-revision summary:focus-visible {
  outline: 3px solid #075a50;
  outline-offset: 3px;
}
.panel-revision {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  display: grid;
  gap: 12px;
  padding: 20px;
  width: 280px;
  max-width: calc(100vw - 40px);
  max-height: calc(100svh - 100px);
  overflow-y: auto;
  border: 1px solid #a9bfb0;
  background: white;
  border-radius: 10px;
  box-shadow: 0 8px 32px #163a2420;
}
.panel-revision p {
  font-size: 12px;
  line-height: 1.65;
}
.panel-revision select {
  width: 100%;
  min-height: 44px;
  font: inherit;
  color: #192c29;
  background: #f1f4f1;
  padding: 8px;
  border: 1px solid #8ca397;
  border-radius: 5px;
}
@media (max-width: 640px) {
  .hero-ingreso {
    display: flex;
    align-items: center;
    padding: 0 4px;
  }
  .hero-ingreso h1 {
    font-size: clamp(42px, 7svh, 56px);
  }
  .hero-ingreso img {
    display: none;
  }
  .hero-secundario {
    padding: 20px 4px;
    min-height: 220px;
  }
  .hero-secundario h1,
  .mensaje-diseno h1 {
    font-size: 44px;
  }
  .hero-secundario p,
  .mensaje-diseno > p {
    font-size: 15px;
  }
  .mensaje-diseno {
    padding: 30px 4px;
  }
  .selector-revision summary {
    padding: 8px 10px;
    min-height: 36px;
    font-size: 11px;
  }
}
@media (max-height: 760px) and (max-width: 560px) {
  .hero-ingreso h1 {
    font-size: 38px;
  }
  .composicion-ingreso {
    gap: 12px;
  }
  .composicion-ingreso :deep(.hoja-acceso) {
    padding: 18px;
  }
  .composicion-ingreso :deep(.titulo-hoja) {
    margin-bottom: 14px;
    gap: 4px;
  }
  .composicion-ingreso :deep(.titulo-hoja h2) {
    font-size: 18px;
  }
  .composicion-ingreso :deep(.campos-ingreso fieldset) {
    gap: 12px;
  }
  .composicion-ingreso :deep(.campo-acceso input) {
    min-height: 44px;
    padding-block: 6px;
  }
  .composicion-ingreso :deep(.pie-hoja) {
    margin-top: 6px;
  }
  .composicion-ingreso :deep(.ver-clave) {
    top: 25px;
  }
}
@media (max-width: 360px) and (max-height: 700px) {
  .composicion-ingreso:has(input[aria-invalid='true']) .hero-ingreso h1 span {
    display: inline;
  }
  .composicion-ingreso:has(input[aria-invalid='true']) :deep(.titulo-hoja p) {
    display: none;
  }
  .composicion-ingreso:has(input[aria-invalid='true']) .hero-ingreso h1 {
    font-size: 24px;
  }
}
</style>
