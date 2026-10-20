# Deconsta · Frontend

Vue 3, TypeScript y Vite. La portada temporal utiliza la identidad Vínculo: verde #075A50, Literata y Manrope, símbolo enlazado y aviso de próxima disponibilidad.

## Desarrollo

Desde la raíz del repositorio:

```sh
pnpm install
pnpm --filter client dev
pnpm --filter client build
pnpm lint:client
pnpm test:client
```

## Marca y metadata

Los recursos de producción están en `public/brand/deconsta/`: logos SVG, favicon SVG/ICO, iconos de aplicación, tarjeta social 1200 × 630, fuentes locales WOFF2 y licencias SIL OFL. El favicon del template se eliminó. Los originales del kit de diseño permanecen fuera del repositorio.

`index.html` centraliza título, descripción, idioma es-PE, colores de tema e iconos. `vite.config.ts` genera las etiquetas que dependen del dominio durante desarrollo y compilación.

Copiar `.env.example` a `.env.local` y definir `VITE_SITE_URL` con la URL pública real antes de compilar para publicar. También puede definirse en el entorno de despliegue. Se espera una URL raíz HTTP(S), sin subdirectorio, credenciales, consulta ni fragmento. No se ha fijado un dominio para esta portada.

Con esa variable se generan canonical, og:url e imagen social absoluta para Open Graph y Twitter. Sin ella se omiten estas etiquetas dependientes del dominio. La portada incluye `noindex, nofollow` mientras está en preparación; revisar la indexación al lanzar el producto. No contiene formulario de registro ni anuncia una fecha de lanzamiento.

La aplicación y sus recursos esperan alojamiento en la raíz del dominio. La tarjeta social debe comprobarse en la URL real después del despliegue. El manifest define identidad e iconos, sin implementar funcionamiento offline.

## Base común de formularios

`main.ts` registra PrimeVue 4.5.5 MIT con Aura 2.0.3 personalizado para Deconsta, textos en español, Toast y
ConfirmDialog. `App.vue` aloja los avisos globales y el router; la portada conserva su propia
página de acceso mientras se implementa H01. Los espacios por rol comparten navegación inferior y cierre visible.

El cliente `http` de `src/api/http.ts` consume VITE_API_URL (por defecto `/api/v1`) a través del
proxy de Vite a 127.0.0.1:8000. En producción, el servidor web debe dirigir `/api` al backend.
Los errores llegan como `{status, code, detail, field}`. Un 401 cierra únicamente la sesión que
hizo esa petición; una respuesta tardía no elimina una sesión nueva. No se reintentan
operaciones automáticamente: un timeout no confirma si el servidor alcanzó a guardarlas.

El store `sesion` conserva token e identidad mínima bajo `deconsta.sesion`; descarta datos
corruptos y funciona en memoria si el navegador impide almacenar. Guardar una identidad local
no sustituye la autorización del backend. Al recargar se comprueba `/auth/me` antes de abrir
un espacio. El instante de última actividad también se conserva para que recargar no reinicie
el plazo de inactividad.

`FormularioBase` recibe `esquema` (objeto Zod), `valoresIniciales`, `guardar` (función asíncrona)
y, opcionalmente, `mensajeExito` y `textoBoton`. Sus hijos `CampoTexto` reciben `nombre`,
`etiqueta`, `ayuda` y `tipo`; los atributos nativos, como autocomplete, se pasan al input.
El esquema debe inicializar todos sus campos, especialmente si usa refine/superRefine.

Los formularios desactivan Guardar sin cambios y durante el envío, muestran errores por campo,
avisan antes de salir y muestran un mensaje de éxito. Sin conexión mantienen el texto en
memoria y permiten editar. No guardan borradores, contraseñas ni datos de pagos en el
almacenamiento del navegador. Al cerrar o recargar la página, ese texto se pierde tras el aviso
normal del navegador. Los componentes se prueban con dos formularios montados de campos
distintos; las pantallas funcionales se implementarán en sus tareas.

La validación usa vee-validate 4 y su adaptador con Zod 3.25, acorde con su peer dependency;
la combinación anterior con Zod 4 era incompatible. La incompatibilidad de FullCalendar sigue
reservada para TASK-59, antes de construir el calendario.

## Acceso, inactividad y tiempo real

`/` lleva a `/login`. Hasta TASK-4, esta ruta conserva la portada de próxima disponibilidad;
no implementa todavía el formulario de acceso. `/gerente` y `/asistente` montan el mismo layout
con identidad y menú del rol confirmado por el backend. Una dirección desconocida muestra
la página no encontrada. Los inicios indican que las herramientas están en preparación;
los paneles y sus datos se implementan en sus historias.

`instalarAcceso` verifica la sesión inicial y protege rutas mediante `meta.rol`. Después del
login, `retornoAutorizado(router, redirect, rol)` permite volver únicamente a una ruta interna
del rol vigente, conservando búsqueda y fragmento. Cada ruta puede definir `meta.titulo`;
el sufijo de la pestaña es Deconsta. Agregar nuevas opciones al menú del layout conforme se
implementen sus pantallas; no declarar acciones que todavía no existen.

El control común registra interacción de teclado, puntero, desplazamiento y tacto. A los
28 minutos sin actividad muestra un aviso con cuenta regresiva y Continuar. Continuar llama
`POST /auth/renovar` y restablece el plazo solo tras una respuesta válida. A los 30 minutos
cierra la sesión. Comprueba fechas absolutas también al volver de una pestaña suspendida;
un temporizador retrasado no concede más tiempo. Si hay actividad reciente, renueva el JWT
cerca de su vencimiento sin cambiar el instante de última actividad.

La actividad, renovación y cierre se coordinan con el evento storage. Si el navegador bloquea
el almacenamiento, la sesión funciona en memoria; la persistencia y coordinación mediante
storage dependen de que el navegador permita ese almacenamiento. No se guardan borradores.
Renovar y comprobar identidad mantienen el formulario montado. El cierre manual avisa si hay
cambios. Una revocación o cierre por inactividad limpia sesión y formularios y lleva al acceso;
la confirmación de cambios no puede bloquear ese cierre.

`controlSesionKey` permite obtener el control compartido. `control.canal.suscribir(callback)`
recibe los eventos del canal común; conservar y ejecutar la función devuelta al desmontar.
Ante conectado o resincronizar, cada módulo debe recuperar sus pendientes por su API: un evento
no constituye el estado del negocio. El control ya vuelve a comprobar `/auth/me` al reconectar,
al recuperar conexión y periódicamente mientras existe sesión.

El canal usa `/api/v1/ws` (o la base `VITE_API_URL`), autentica en el primer mensaje y no coloca
el token en la URL. Al renovar abre otro socket y espera conectado antes de cerrar el anterior.
Los cierres tardíos del token anterior se descartan; un 4401 del token vigente cierra la sesión
con su motivo. Los fallos de transporte reconectan con espera creciente hasta 30 segundos.
En producción el proxy debe permitir Upgrade de WebSocket. No se reintentan pagos ni escrituras.

Validación de TASK-107: pruebas de ambos roles, retorno autorizado, errores de red y 401,
revocación, relojes de 28/30 minutos, suspensión, respuestas tardías, pestañas y formularios.
También se verificaron en navegador ambos roles contra FastAPI, renovación, revocación real
por WebSocket y cierre entre pestañas; las cuentas temporales de prueba se eliminaron.
