<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import Button from 'primevue/button'
import ProntoPage from './ProntoPage.vue'
import { controlSesionKey } from '@/services/controlSesion'
import { retornoAutorizado } from '@/router/guard'
const route = useRoute()
const router = useRouter()
const control = inject(controlSesionKey, null)
const comprobando = ref(false)
const noEncontrada = computed(() => route.name === 'no-encontrada')
const mensajes: Record<string, string> = {
  inactividad: 'Cerramos tu sesión tras 30 minutos sin actividad.',
  SESION_REVOCADA: 'Tu sesión fue revocada. Tendrás que iniciar sesión de nuevo.',
  CUENTA_INACTIVA: 'Tu cuenta ya no está activa. Contacta con tu gerente.',
  NO_AUTENTICADO: 'Tu sesión venció. Tendrás que iniciar sesión de nuevo.',
  'otra-pestana': 'La sesión se cerró desde otra pestaña.',
  'sin-conexion': 'No pudimos comprobar tu sesión. Revisa tu conexión y vuelve a intentar.',
}
const mensaje = computed(() => mensajes[String(route.query.motivo)] || '')
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
</script>
<template>
  <div v-if="noEncontrada" class="no-encontrada">
    <img
      src="/brand/deconsta/logo/deconsta-wordmark-white.svg"
      alt="Deconsta"
      width="176"
      height="35"
    />
    <main>
      <p>Esta dirección no está disponible.</p>
      <h1>No encontramos esa página.</h1>
      <RouterLink :to="{ name: 'login' }">Volver al inicio</RouterLink>
    </main>
    <Button
      v-if="control?.sesion.token"
      label="Cerrar sesión"
      severity="secondary"
      @click="control.sesion.cerrar()"
    />
  </div>
  <div v-else>
    <aside v-if="mensaje" class="aviso-acceso" role="status">
      <p>{{ mensaje }}</p>
      <Button
        v-if="control?.sesion.token"
        label="Reintentar"
        :loading="comprobando"
        @click="reintentar"
      />
    </aside>
    <ProntoPage />
  </div>
</template>
<style scoped>
.aviso-acceso {
  background: #fff;
  color: #192c29;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px clamp(24px, 5vw, 80px);
}
.aviso-acceso p {
  margin: 0;
  max-width: 70ch;
  line-height: 1.6;
}
.no-encontrada {
  min-height: 100svh;
  padding: clamp(28px, 5vw, 80px);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 60px;
}
h1 {
  font-family: Literata, Georgia, serif;
  font-size: clamp(2rem, 5vw, 4rem);
  font-weight: 500;
}
a {
  color: white;
  text-underline-offset: 5px;
}
</style>
