<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useConfirm } from 'primevue/useconfirm'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { controlSesionKey } from '@/services/controlSesion'
import { useSesionStore } from '@/stores/sesion'
import { INICIO_POR_ROL } from '@/router/guard'
import PestanasEspacio from '@/components/espacio/PestanasEspacio.vue'
import MenuCuenta from '@/components/espacio/MenuCuenta.vue'
import ModalPolitica from '@/components/cuenta/ModalPolitica.vue'
import { obtenerPerfil } from '@/api/acceso'

// El espacio es la hoja del acceso llevada al trabajo diario: la mesa verde enmarca, las
// pestañas de índice salen del borde de la hoja y la cuenta queda siempre a mano (RG08).
const sesion = useSesionStore()
const control = inject(controlSesionKey, null)
const confirmacion = useConfirm()
const router = useRouter()
const rol = computed(() => sesion.rol || 'gerente')
const inicio = computed(() => INICIO_POR_ROL[rol.value])
// H02 CA10: falta aceptar la política si la versión aceptada no es la vigente. Si el perfil no
// carga, no se interrumpe el trabajo: se vuelve a comprobar al entrar de nuevo al espacio.
const politicaPendiente = ref(false)
onMounted(async () => {
  try {
    const perfil = await obtenerPerfil()
    politicaPendiente.value =
      !!perfil.politica_vigente && perfil.politica_version !== perfil.politica_vigente
  } catch {
    politicaPendiente.value = false
  }
})
// Lo que llega por tiempo real se avisa al momento; el gerente se entera así del voucher que
// tiene que validar (TASK-109). El centro de notificaciones es TASK-98.
const toast = useToast()
const dejarDeEscuchar = control?.canal.suscribir((evento) => {
  if (evento.tipo !== 'notificacion' || !evento.datos?.aviso) return
  const datos = evento.datos as { titulo?: string; mensaje?: string; deuda_id?: string | null }
  toast.add({
    group: 'notificacion',
    severity: 'info',
    summary: datos.titulo,
    // detail admite cualquier valor: lleva el texto y la deuda para el enlace «Ver la deuda».
    detail: { texto: datos.mensaje, deuda: datos.deuda_id ?? null },
    life: 12000,
  })
})
onBeforeUnmount(() => dejarDeEscuchar?.())

function verDeuda(id: string) {
  toast.removeGroup('notificacion')
  void router.push({ name: `${rol.value}-deuda`, params: { id } })
}

function cerrar() {
  const salir = () => {
    sesion.cerrar()
    void router.replace({ name: 'login' })
  }
  if (!control?.hayCambios()) {
    salir()
    return
  }
  confirmacion.require({
    header: 'Cambios sin guardar',
    message: 'Si cierras sesión, perderás lo que estás editando.',
    acceptLabel: 'Cerrar sin guardar',
    rejectLabel: 'Seguir editando',
    defaultFocus: 'reject',
    accept: salir,
  })
}
</script>

<template>
  <div class="espacio">
    <a class="saltar" href="#contenido">Ir al contenido</a>
    <header class="borde-mesa">
      <RouterLink :to="{ name: inicio }" class="marca" aria-label="Deconsta, inicio">
        <img
          src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
          alt="Deconsta"
          width="132"
          height="26"
        />
      </RouterLink>
      <MenuCuenta v-if="sesion.usuario" :usuario="sesion.usuario" @cerrar="cerrar" />
    </header>
    <PestanasEspacio :rol="rol" />
    <main id="contenido" class="hoja" tabindex="-1"><RouterView /></main>
    <ModalPolitica v-if="politicaPendiente" @aceptada="politicaPendiente = false" @salir="cerrar" />
    <Toast group="notificacion" position="bottom-right">
      <template #message="{ message }">
        <div class="aviso">
          <strong>{{ message.summary }}</strong>
          <p>{{ message.detail.texto }}</p>
          <button v-if="message.detail.deuda" type="button" @click="verDeuda(message.detail.deuda)">
            Ver la deuda
          </button>
        </div>
      </template>
    </Toast>
  </div>
</template>

<style scoped>
.aviso {
  display: grid;
  flex: 1;
  gap: 4px;
}
.aviso p {
  margin: 0;
  font-size: var(--texto-sm);
  line-height: 1.45;
}
.aviso button {
  justify-self: start;
  margin-top: 6px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--deconsta-primary);
  font: inherit;
  font-weight: 700;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}
.espacio {
  display: flex;
  flex-direction: column;
  min-height: 100svh;
  padding: 0 var(--margen-mesa) var(--margen-mesa);
  background: var(--deconsta-primary);
  color: var(--deconsta-paper);
}
.borde-mesa {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 72px;
}
.marca {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  border-radius: 4px;
}
.marca img {
  display: block;
  width: clamp(112px, 10vw, 132px);
  height: auto;
}
.marca:focus-visible {
  outline: 3px solid var(--deconsta-paper);
  outline-offset: 6px;
}
.hoja {
  flex: 1;
  min-width: 0;
  padding: clamp(24px, 4vw, 56px);
  border-radius: var(--radio-hoja);
  background: var(--deconsta-paper);
  color: var(--deconsta-ink);
  outline: none;
}
/* Si la primera pestaña está abierta, la hoja continúa recta bajo ella. */
.espacio:has(.pestanas li:first-child a.activa) .hoja {
  border-top-left-radius: 0;
}
.saltar {
  position: fixed;
  top: -100px;
  left: 16px;
  z-index: 30;
  padding: 16px;
  background: var(--deconsta-paper);
  color: var(--deconsta-primary);
}
.saltar:focus {
  top: 12px;
}
@media (max-width: 767px) {
  .borde-mesa {
    min-height: 60px;
  }
  .hoja {
    padding: 24px 20px 32px;
    border-radius: 5px 28px 5px 5px;
  }
}
</style>
