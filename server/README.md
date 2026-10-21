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

## Tareas en segundo plano: Celery y Beat

El worker de Celery ejecuta las tareas en segundo plano y Beat las programa. Los dos usan el
Redis de `REDIS_URL` como broker y backend de resultados, y abren sus sesiones de base con la
misma configuración que la API (`DATABASE_URL`). No necesitan variables de entorno nuevas.

| Archivo | Contenido |
|---|---|
| `app/workers/celery_app.py` | App de Celery y su configuración |
| `app/workers/horarios.py` | Horarios de Beat |
| `app/workers/base.py` | Base de las tareas: reintentos, sesión propia y bloqueo |
| `app/workers/encolar.py` | Encolar una tarea solo si la transacción se confirma |
| `app/workers/latido.py` | Latido: job de ejemplo que comprueba que todo responde |
| `app/workers/aprobaciones.py` | Recordatorios de solicitudes de aprobación pendientes (H05) |
| `app/workers/comprobantes.py` | Validación de comprobantes en la cola `ocr` y su recuperación (H24) |

### Arranque local

Requiere los servicios levantados (`pnpm services:up`) y la base migrada.

```bash
pnpm dev             # client, server, worker y beat
pnpm worker:server   # solo el worker, en otra terminal
pnpm beat:server     # solo Beat, en otra terminal
pnpm worker:ocr      # worker de la cola ocr (ver OCR de comprobantes)
```

El worker escucha la cola `general` con dos procesos y se reinicia solo cuando cambia un archivo
de `server/app`. En macOS los procesos del worker se crean con spawn en lugar de fork, y Celery
solo los prepara para ejecutar tareas si existe la variable `FORKED_BY_MULTIPROCESSING=1`, que
`pnpm worker:server` ya define. Si arrancas `celery worker` a mano en macOS, defínela tú; sin
ella toda tarea falla con `not enough values to unpack`. En Linux no hace falta. Beat no se reinicia solo: al cambiar `horarios.py`, detenlo y arráncalo otra
vez. Beat guarda su estado en `server/celerybeat-schedule*`, que no se sube al repositorio.

Para comprobar que funcionan, espera a que corra el latido (cada 5 minutos, a las :00, :05,
:10...) y lee su registro:

```bash
docker compose exec redis redis-cli GET control_pagos:latido
```

Devuelve la hora de Lima de la última ejecución y la hora de la base. La clave vence a los
15 minutos: si no existe, el worker o Beat están detenidos.

### OCR de comprobantes

La validación de comprobantes (H24) corre en su propia cola, `ocr`, con un worker de un solo
proceso que precarga PaddleOCR al arrancar. Así una lectura de unos segundos no retrasa los
recordatorios de la cola `general`. La API y el worker general no instalan ni importan el OCR.

```bash
brew install poppler          # macOS; en Debian o Ubuntu: apt install poppler-utils
pnpm worker:ocr               # en otra terminal; la primera vez instala el grupo ocr
```

`pnpm worker:ocr` ejecuta `uv run --group ocr`, que instala PaddleOCR (cerca de 1 GB), y la
primera lectura descarga los modelos de español en `~/.paddlex`. Poppler (`pdftoppm`) convierte
los PDF en imágenes. Sin el worker de OCR levantado, los comprobantes se quedan en `procesando`
y la revisión programada los vuelve a encolar cuando el worker arranca.

| Paso | Dónde | Qué hace |
|---|---|---|
| Subida | `app/services/comprobantes.py` | Guarda el archivo y encola `procesar_comprobante` tras el commit |
| Lectura | `app/ocr/motor.py` | PDF hasta 2 páginas a 200 ppp; imágenes reducidas a 2000 px; texto y confianza por línea |
| Resultado | `app/services/validacion.py` | Ilegible (sin texto o confianza menor a 0,6): rechazado. Con texto: revisión del gerente hasta que existan extractores y reglas |
| Avisos | `app/services/validacion.py` | Notificación y evento `comprobante_resultado` después del commit |
| Recuperación | `recuperar_comprobantes`, cada 5 minutos | Vuelve a encolar lo que lleva 10 minutos en `procesando`; a la tercera vez lo deja en revisión |

Cada lectura tiene 45 s de límite y se reintenta 2 veces (a los 10 s y a los 20 s) si falla el
OCR, la conversión del PDF o S3. Agotados los reintentos, el comprobante pasa a revisión del
gerente con la explicación: nunca se pierde el registro. La tarea es idempotente: si el
comprobante ya no está en `procesando`, termina sin efectos.

Medición del objetivo de 10 s (contrato H24, punto 7): `tests/test_ocr_motor.py` lee con el
modelo ya cargado un comprobante sintético de una página. En un Mac con Apple Silicon (CPU, sin
GPU) tarda 2,3 s; la carga del modelo, que se hace una vez por proceso, tarda unos 10 s. La
prueba se omite si el grupo `ocr` no está instalado, como en la CI.

### Configuración

| Opción | Valor | Por qué |
|---|---|---|
| Formato de los mensajes | Solo JSON | Los argumentos son ids como texto, nunca objetos del ORM |
| Zona de Beat | `TIMEZONE` (America/Lima) | Las horas de crontab se leen en Lima; Celery trabaja en UTC |
| Confirmación del mensaje | Al terminar la tarea, uno a la vez por proceso | Un mensaje no se pierde si el worker se detiene antes de ejecutarlo |
| Límite de tiempo | 60 s aviso y 90 s corte | Cada tarea puede fijar los suyos (`soft_time_limit`, `time_limit`) |
| Reintentos | Hasta 3, esperando 5 s, 10 s, 20 s... (máximo 300 s, con variación) | Solo ante fallos transitorios de la base o de Redis; un error de lógica no se reintenta |
| Resultados | Se ignoran salvo que se pidan | El estado vive en la base y llega por la API y el WebSocket |
| Encargo programado (`countdown`, `eta`) | Menos de una hora | Pasada una hora sin confirmarse, Redis lo entrega otra vez |

Si un proceso del worker muere a mitad de una tarea, esta no se reencola sola: la recupera la
revisión programada que le corresponde. Por eso los plazos (por ejemplo, avisar a los 10 minutos
o a las 4 horas) se implementan con una revisión periódica de Beat y no con `countdown`.

### Agregar una tarea programada

1. Crear la tarea en un módulo de `app/workers/` con `@celery_app.task`. Toda tarea usa la base
   común (`TareaBase`) sin declararla.
2. Agregar el módulo al `include` de `app/workers/celery_app.py`.
3. Agregar su entrada en `HORARIOS` (`app/workers/horarios.py`), con `expires` menor o igual a su
   intervalo para que los encargos atrasados no se acumulen:

```python
"recordatorios_comprobante": {
    "task": "app.workers.recordatorios.revisar_comprobantes",
    "schedule": crontab(minute="*/15"),  # cada 15 minutos; crontab(hour=18, minute=0) a las 18:00
    "options": {"expires": 14 * 60},
},
```

Una prueba de `tests/test_workers_config.py` falla si una entrada apunta a una tarea que no está
registrada o no tiene `expires`. Beat corre en una sola instancia.

### Patrón de un job

Cada ejecución comprueba el estado actual y es idempotente: correr el job dos veces, o volver a
recibir el mismo mensaje, no duplica efectos.

```python
@celery_app.task(soft_time_limit=50, time_limit=60)
def revisar_comprobantes() -> None:
    with un_solo_a_la_vez("revisar_comprobantes") as tomado:
        if not tomado:
            return  # otra ejecución sigue en curso
        with sesion_de_trabajo() as db:  # sesión propia; confirma al salir, deshace si falla
            for deuda in candidatas(db):  # elegidas por su estado actual
                # Se vuelve a comprobar el estado dentro de la transacción y el aviso usa
                # clave_evento: repetirlo no crea otra notificación.
                notificar(db, ..., clave_evento=f"recordatorio:{deuda.id}:{ciclo}")
```

- `un_solo_a_la_vez` toma un bloqueo en Redis que vence solo a los 120 s si el worker muere.
- `sesion_de_trabajo` confirma la transacción al salir sin errores y la deshace si hay una
  excepción. Los eventos (`publicar_tras_commit`, `notificar`) y las tareas encoladas con
  `encolar_tras_commit` salen solo después del commit.
- La idempotencia la garantiza la base: condición de estado al actualizar, unicidades y
  `clave_evento`. El bloqueo solo evita trabajo simultáneo.

### Encolar desde un servicio

Un servicio que necesita trabajo en segundo plano lo encola en su misma sesión:

```python
encolar_tras_commit(db, procesar_comprobante.s(str(comprobante.id)))
```

La tarea se envía solo si la transacción se confirma; si se deshace, no se encola nada. Si Redis
no responde al encolar, el commit se conserva y el fallo queda en el log, sin los argumentos de la
tarea. Por eso el trabajo encolado así deja en la base un estado (por ejemplo, un comprobante en
`procesando`) que una revisión de Beat recorre para volver a encolarlo, y la tarea es idempotente
ante ese segundo envío.

### Pruebas

- Las tareas se prueban con `tarea.apply()`, que las ejecuta en el mismo proceso, con sus
  reintentos y sin esperar entre ellos.
- Para que un job use la sesión de la prueba, se reemplaza `app.workers.base.fabrica_sesiones`.
- `tests/test_latido.py` arranca un worker real dentro de la prueba, sobre una cola con nombre
  único que no consume el worker local. Al terminar borra la cola, su registro y las claves de
  la prueba en Redis.
