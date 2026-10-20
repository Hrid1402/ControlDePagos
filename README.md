# Control de Pagos

Sistema web para que un gerente delegue a su asistente el pago de servicios y deudas, con órdenes
de pago, límites y aprobaciones, comprobantes y notificaciones en tiempo real.

| Carpeta | Contenido |
|---|---|
| `client/` | Interfaz web: Vue 3, Vite y TypeScript. Ver [client/README.md](client/README.md) |
| `server/` | API (FastAPI, SQLAlchemy y Alembic), worker y Beat de Celery. Ver [server/README.md](server/README.md) |
| `docker/` | Configuración de los servicios locales de `compose.yaml` |

La especificación, las historias y la guía de trabajo están en Notion.

## Desarrollo local

Requisitos: Node (versión de `.nvmrc`) con corepack, uv y Docker.

```bash
corepack enable
pnpm install
(cd server && uv sync)
cp server/.env.example server/.env
pnpm services:up                      # Postgres, Redis, Mailpit y SeaweedFS
(cd server && uv run alembic upgrade head)
pnpm init:gerente                     # crea el primer gerente; ver server/README.md
pnpm dev                              # client, server, worker y Beat
```

El client queda en http://localhost:5173 y llama a la API por el proxy de Vite. Antes de abrir
una PR, `pnpm check` ejecuta el lint y las pruebas de las dos partes.

## Despliegue

Producción corre en Railway y se despliega sola desde `main`. El flujo es:

```txt
dev  ->  PR de dev hacia main  ->  fusión  ->  Railway construye y despliega los servicios
```

### Servicios

| Servicio | Carpeta raíz | Archivo de configuración | Qué hace |
|---|---|---|---|
| Postgres | — | — | Base de datos (plantilla de Railway) |
| Redis | — | — | Broker de Celery y eventos del tiempo real (plantilla de Railway) |
| server | `/server` | `/server/railway.json` | API. Antes de cada despliegue ejecuta `alembic upgrade head` |
| worker | `/server` | `/server/railway.worker.json` | Worker de Celery |
| beat | `/server` | `/server/railway.beat.json` | Beat de Celery, siempre una sola réplica |
| client | `/` | `/client/railway.json` | Caddy: sirve la SPA y reenvía `/api` al server |

server, worker y beat usan la misma imagen (`server/Dockerfile`) con distinto comando de
arranque. El client (`client/Dockerfile`) se construye desde la raíz porque necesita el lockfile
de pnpm. Solo el client tiene dominio público: el navegador ve un único dominio, sin CORS, y
Caddy reenvía `/api/*`, incluido el WebSocket `/api/v1/ws`, al server por la red privada. Por
eso `/docs` y `/openapi.json` del server no se alcanzan desde fuera.

### Variables

Las comunes se crean como variables compartidas del proyecto y cada servicio las referencia con
`${{shared.NOMBRE}}`. server, worker y beat necesitan todas, porque la configuración del server
las exige al arrancar. Los valores secretos solo se escriben en Railway, nunca en el repositorio.

| Variable | Servicios | Valor |
|---|---|---|
| `DATABASE_URL` | server, worker, beat | `postgresql+psycopg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}` |
| `REDIS_URL` | server, worker, beat | `${{Redis.REDIS_URL}}` |
| `JWT_SECRET` | server, worker, beat | Compartida. Generada (ver el paso 3) |
| `URL_CLIENTE` | server, worker, beat | `https://${{client.RAILWAY_PUBLIC_DOMAIN}}` |
| `CORS_ORIGINS` | server | `["https://${{client.RAILWAY_PUBLIC_DOMAIN}}"]` |
| `PORT` | server | `8000` |
| `SMTP_HOST` | server, worker, beat | Compartida. `correo.sin-configurar.invalid` (ver Pendientes) |
| `SMTP_PORT` | server, worker, beat | Compartida. `587` |
| `SMTP_FROM` | server, worker, beat | Compartida. `no-responder@sin-configurar.invalid` |
| `SMTP_TLS` | server, worker, beat | Compartida. `false` |
| `S3_ENDPOINT` | server, worker, beat | Compartida. `https://almacenamiento.sin-configurar.invalid` |
| `S3_REGION` | server, worker, beat | Compartida. `us-east-1` |
| `S3_BUCKET` | server, worker, beat | Compartida. `control-pagos` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | server, worker, beat | Compartidas. `sin-configurar` |
| `POLITICA_DOMICILIO`, `POLITICA_CORREO` | server, worker, beat | Compartidas. Ver Pendientes |
| `API_UPSTREAM` | client | `${{server.RAILWAY_PRIVATE_DOMAIN}}:${{server.PORT}}` |
| `VITE_SITE_URL` | client | Opcional: `https://${{RAILWAY_PUBLIC_DOMAIN}}` |

Railway entrega `postgresql://` en su `DATABASE_URL`, pero el server usa el driver psycopg 3
(`postgresql+psycopg://`); por eso la URL se arma con las referencias de la tabla. Los dominios
`.invalid` no existen: el envío de correo falla en segundo plano y queda en el log, sin afectar
la respuesta de la API. S3 todavía no se usa.

### Pasos en Railway

Se hacen una sola vez, cuando `main` ya tiene estos archivos.

1. Instalar la CLI de Railway e iniciar sesión (`railway login`).
2. Crear el proyecto y agregar Postgres y Redis desde sus plantillas. Comprobar que Postgres sea
   la versión 17. En la pestaña Networking de cada uno, quitar el proxy TCP público si lo tiene:
   solo se usan por la red privada.
3. En Project Settings, Shared Variables, crear las variables compartidas de la tabla. Para
   `JWT_SECRET`, generar el valor y copiarlo al portapapeles sin que quede en el historial:

   ```bash
   openssl rand -base64 64 | tr -d '\n' | pbcopy
   ```

   Pegarlo en Railway y copiar después otra cosa para vaciar el portapapeles.
4. Crear el servicio **server** desde el repositorio de GitHub:
   - Settings, Source: rama `main` y carpeta raíz `/server`.
   - Settings, Config-as-code: `/server/railway.json`. La ruta es absoluta desde la raíz del
     repositorio, aunque la carpeta raíz del servicio sea `/server`.
   - Variables: las de la tabla para server. No generar dominio público.
5. Crear **worker** y **beat** igual que el server, con `/server/railway.worker.json` y
   `/server/railway.beat.json`, sus variables y sin dominio público.
6. Crear el servicio **client** desde el mismo repositorio: rama `main`, carpeta raíz `/`,
   archivo `/client/railway.json` y las variables del client. En Networking, generar el dominio
   público.
7. Con el dominio del client creado, revisar que `URL_CLIENTE` y `CORS_ORIGINS` lo muestren
   resuelto y redesplegar server, worker y beat.
8. Comprobar el despliegue:
   - En el registro del server, el paso previo muestra `alembic upgrade head` sin errores.
   - `https://<dominio>/` carga la aplicación y una ruta interna recargada no da 404.
   - El inicio de sesión funciona y el aviso de conexión en tiempo real aparece.
   - A los 5 minutos corre el latido de Celery. Desde una consola del server
     (`railway ssh --service server`):

     ```bash
     python -c "import redis; from app.core.config import settings; print(redis.Redis.from_url(settings.redis_url).get('control_pagos:latido'))"
     ```
9. Inicializar el gerente (siguiente apartado).

Desde entonces, cada fusión en `main` despliega sola los servicios cuyos archivos cambiaron.
Para volver a una versión anterior se usa Rollback en el servicio; las migraciones no se
deshacen solas.

### Inicializar el gerente en producción

La imagen no tiene pnpm: el equivalente de `pnpm init:gerente` es
`python -m app.comandos.inicializar_gerente`, dentro del contenedor del server.

```bash
railway link                       # una vez: proyecto y entorno production
railway ssh --service server
# dentro del contenedor:
GERENTE_USERNAME=edward.castillo GERENTE_NOMBRES="Edward Fernando" GERENTE_APELLIDOS="Castillo Robles" python -m app.comandos.inicializar_gerente
```

El comando pide la contraseña sin mostrarla y la confirma. No se escribe en la línea del comando
ni en una variable de Railway. El correo es opcional: el gerente lo completa después en Mi
cuenta. Los códigos de salida y las reglas de la contraseña están en
[server/README.md](server/README.md#inicializar-el-gerente).

### Red privada

El server escucha en `0.0.0.0`. La red privada de Railway resuelve IPv4 en los entornos creados
desde el 16 de octubre de 2025. Si el proyecto estuviera en un entorno anterior, solo con IPv6,
Caddy no alcanzaría al server: en ese caso, cambiar `--host 0.0.0.0` por `--host ::` en el `CMD`
de `server/Dockerfile`.

El server confía en las cabeceras de proxy porque solo recibe tráfico del client. Por eso no debe
tener dominio público. Caddy toma la IP real del usuario de la cabecera `X-Real-IP` que pone
Railway y descarta el `X-Forwarded-For` que envía el navegador.

### Probar las imágenes en local

Con los servicios de `compose.yaml` levantados y un archivo de variables fuera del repositorio
(como `server/.env.example`, pero con los hosts `postgres` y `redis` de la red de compose):

```bash
docker build -t cdp-server server
docker build -f client/Dockerfile -t cdp-client .
docker run --rm --network control-de-pagos_default --env-file <archivo> cdp-server alembic upgrade head
docker run -d --name cdp-server --network control-de-pagos_default --network-alias server --env-file <archivo> cdp-server
docker run -d --name cdp-client --network control-de-pagos_default -e API_UPSTREAM=server:8000 -p 8080:8080 cdp-client
```

La aplicación queda en http://localhost:8080. La CI construye las dos imágenes en cada PR que
cambia `server/` o `client/`.

## Pendientes

- **Correo.** Railway bloquea el SMTP saliente en los planes Free, Trial y Hobby. Hasta que el
  envío use la API HTTPS de Brevo, la recuperación de contraseña responde normalmente pero no
  envía el correo. Mientras tanto, el gerente puede restablecer la contraseña de su asistente
  desde la gestión de asistentes.
- **Política de privacidad.** Completar `POLITICA_DOMICILIO` y `POLITICA_CORREO` con los datos
  reales del responsable: la política los muestra a cada usuario.
- **Almacenamiento S3.** Reemplazar los valores provisionales de `S3_*` cuando se implemente la
  carga de archivos.
