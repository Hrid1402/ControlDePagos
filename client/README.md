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
página. Los layouts por rol y el control de inactividad pertenecen a TASK-107.

El cliente `http` de `src/api/http.ts` consume VITE_API_URL (por defecto `/api/v1`) a través del
proxy de Vite a 127.0.0.1:8000. En producción, el servidor web debe dirigir `/api` al backend.
Los errores llegan como `{status, code, detail, field}`. Un 401 cierra únicamente la sesión que
hizo esa petición; una respuesta tardía no elimina una sesión nueva. No se reintentan
operaciones automáticamente: un timeout no confirma si el servidor alcanzó a guardarlas.

El store `sesion` conserva token e identidad mínima bajo `deconsta.sesion`; descarta datos
corruptos y funciona en memoria si el navegador impide almacenar. Guardar una identidad local
no sustituye la autorización del backend. TASK-107 verificará la sesión al recargar e integrará
revocación, inactividad y coordinación entre pestañas.

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
