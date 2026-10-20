# TASK-1 · Diseño de acceso de Deconsta

El login es la raíz `/`. `/login` redirige a ella conservando query y hash.
Se reemplaza la portada temporal y se elimina el prototipo HTML anterior.

## Alcance

Diseño Vue de H01: acceso, recuperación, restablecimiento y página sin permiso
(CA03, CA05 y CA11). Incluye validación local, mostrar/ocultar contraseña,
estados de carga/error y navegación. Se conserva el reintento de sesión y el
retorno autorizado de TASK-107.

Los formularios emiten datos validados. TASK-4 conectará login, recuperación y
restablecimiento con la API. Mientras tanto, un envío válido muestra que la opción
estará disponible pronto; no crea una sesión ni anuncia un correo enviado o una
contraseña guardada. El historial de contraseñas y los tokens se validarán en servidor.

Bienvenida, perfil, medios de pago, tutorial, categorías y deudas quedan fuera de
esta entrega. Se retiraron sus componentes, estado y pruebas del borrador.

## Organización

- `components/acceso/MarcoAcceso.vue`: marca, altura de pantalla y estructura.
- `components/acceso/CampoAcceso.vue`: adapta CampoTexto común y revela la clave.
- `components/acceso/FormularioIngreso.vue`: usuario/contraseña y validación.
- `components/acceso/FormularioRecuperacion.vue`: correo y validación de formato.
- `components/acceso/FormularioClave.vue`: requisitos y confirmación de clave.
- `pages/AccesoPage.vue`: pantallas, mensajes y navegación.
- `types/acceso.ts`: contratos de formularios y estados de acceso.
- `assets/acceso.css`: estilos comunes limitados al marco de acceso.

## Rutas y revisión

- `/`: acceso.
- `/recuperar`: solicitud de recuperación.
- `/restablecer/:token?`: nueva contraseña (la integración validará el token).
- `/sin-permiso`: retorno al espacio autorizado o cierre de sesión.
- Direcciones inexistentes: mensaje y retorno al inicio.

Solo en desarrollo, `/?revision=1` abre el selector de estados visuales. Permite
inspeccionar carga, errores, bloqueo, inactividad, éxito y enlace vencido/usado.
Los estados de éxito requieren selección explícita en esa revisión; enviar un
formulario no simula operaciones. Los controles no están disponibles en producción.
La dirección anterior `/revision/acceso` redirige al catálogo local.

## Composición y accesibilidad

Identidad verde Vínculo #075A50, papel #F1F4F1, tinta #192C29, Literata y Manrope.
Formulario horizontal en escritorio y vertical en móvil. El login ocupa 100svh
sin scroll sobrante; título y decoración ceden espacio antes que los controles.
Con zoom, teclado o altura reducida se permite desplazamiento para mantener el acceso.

Los campos usan labels, autocomplete, errores asociados y foco visible. Se permite
pegar y usar gestores; las contraseñas no se recortan. La carga conserva lo escrito.
Se respeta prefers-reduced-motion. La respuesta de recuperación diseñada no revela
si existe la cuenta. Se reutilizan CampoTexto y Zod/vee-validate de TASK-106.

## Referencias

- [Vue: formularios](https://vuejs.org/guide/essentials/forms.html).
- [W3C: reflow](https://www.w3.org/WAI/WCAG21/Understanding/reflow).
