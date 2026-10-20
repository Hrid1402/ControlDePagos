# Server

API de Control de Pagos (FastAPI, SQLAlchemy y Alembic). Los comandos de desarrollo se ejecutan
desde la raíz del repositorio con pnpm; ver `package.json`.

## Inicializar el gerente

No hay registro público de gerentes. Cada gerente se crea con un comando administrativo, que
también le crea sus categorías precargadas: Luz, Agua, Gas, Telefonía e internet, Tarjeta de
crédito, Préstamo y Otros.

Requiere la base migrada (`cd server && uv run alembic upgrade head`) y usa la `DATABASE_URL` de
`server/.env`.

En cada ejecución también sincroniza el catálogo de empresas comunes que se eligen al registrar
un servicio (Hidrandina, Enel, Luz del Sur, Sedalib, Sedapal, Cálidda, Quavii, Movistar, Claro,
Entel y Bitel). El catálogo es uno solo para todos los gerentes y está en
`app/services/empresas.py`. **Si ya tienes tu gerente creado, vuelve a ejecutar
`pnpm init:gerente` con su username para cargar las empresas**: no cambia su contraseña ni sus
datos. Cuando se agrega a la constante el patrón verificado del código de suministro de una
empresa, ejecutarlo de nuevo lo aplica.

### Uso interactivo (recomendado)

```bash
export GERENTE_USERNAME=rosa.diaz
pnpm init:gerente
```

Si falta `GERENTE_USERNAME`, el comando lo pide. Si hay que crear la cuenta, pide la contraseña
sin mostrarla y la confirma.

### Uso con variables (CI o contenedores)

El comando lee las variables del entorno de la sesión, no del archivo `.env`.

| Variable | Obligatoria | Regla |
|---|---|---|
| `GERENTE_USERNAME` | Sí | De 3 a 30 caracteres: letras sin tildes, números, `.`, `-` o `_` |
| `GERENTE_CONTRASENA` | Solo para crear | Mínimo 8 caracteres, con mayúscula, minúscula, número y símbolo; máximo 72 bytes |
| `GERENTE_NOMBRES` | No | Solo letras, con tildes y ñ |
| `GERENTE_APELLIDOS` | No | Solo letras, con tildes y ñ |
| `GERENTE_CORREO` | No | Correo válido que no use otra cuenta; habilita la recuperación de contraseña |

Nunca escribas la contraseña en la misma línea del comando ni en un `export`: quedaría en el
historial del shell. Léela sin eco en una línea aparte:

```bash
export GERENTE_USERNAME=rosa.diaz
read -rs GERENTE_CONTRASENA && export GERENTE_CONTRASENA
pnpm init:gerente
unset GERENTE_CONTRASENA
```

O cárgala desde un archivo fuera del repositorio, legible solo por ti:

```bash
# ~/secretos/gerente.env contiene GERENTE_USERNAME=... y GERENTE_CONTRASENA=...
chmod 600 ~/secretos/gerente.env
set -a && . ~/secretos/gerente.env && set +a
pnpm init:gerente
unset GERENTE_USERNAME GERENTE_CONTRASENA
```

En CI, usa los secretos del proveedor como variables de entorno.

### Ejecutarlo de nuevo

El comando es idempotente: se puede ejecutar varias veces, incluso en paralelo, sin duplicar
cuentas ni categorías. El username se compara sin distinguir mayúsculas.

| Situación | Resultado |
|---|---|
| El username no existe | Crea el gerente activo y sus categorías precargadas |
| Ya es de un gerente activo | No cambia su contraseña ni sus datos; solo crea las precargadas que falten y avisa si los datos indicados son distintos |
| Ya hay una categoría propia con el nombre de una precargada | La deja como está y avisa |
| Es de una asistente, de un gerente inactivo o de una cuenta eliminada | Conflicto, sin cambios |
| El correo ya lo usa otra cuenta | Conflicto, sin cambios |
| Faltan empresas comunes o hay un patrón nuevo en la constante | Crea las que faltan y aplica el patrón; no duplica ni borra empresas |

Un username distinto crea otro gerente con sus propias categorías.

La contraseña no se muestra, no se registra en la auditoría y no queda en ningún registro.

### Códigos de salida

| Código | Significado |
|---|---|
| 0 | Gerente creado o ya existente |
| 1 | Error inesperado de la base de datos |
| 2 | Dato faltante o inválido |
| 3 | Conflicto con una cuenta existente |
| 130 | Interrumpido con Ctrl+C |

## Contraseñas e historial

La creación de cuentas, el cambio y el restablecimiento usan la misma regla: mínimo 8
caracteres, con mayúscula, minúscula, número y símbolo, y máximo 72 bytes UTF-8. Los espacios
no se recortan. La API devuelve 422 con el campo y un motivo de validación sin exponer la
contraseña recibida.

El cambio y el restablecimiento rechazan la contraseña actual y las tres anteriores. El hash
actual vive en usuario; al sustituirlo se agrega al historial y se incrementa token_version.
Las cuentas nuevas no tienen contraseñas anteriores. Los registros antiguos se conservan:
el lector omite el hash vigente y hashes repetidos para no reducir la ventana de tres.

No requiere migración ni limpieza de datos existentes. El cambio propio conserva la sesión
actual mediante un token renovado; el restablecimiento exige iniciar sesión otra vez.
