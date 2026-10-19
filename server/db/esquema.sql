-- Control de Pagos: esquema de la base de datos

-- Funciones

CREATE FUNCTION uuid_generate_v7() RETURNS uuid AS $$
DECLARE
  marca bytea;
  bytes bytea;
BEGIN
  marca := substring(int8send(floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint) FROM 3);
  bytes := uuid_send(gen_random_uuid());
  bytes := overlay(bytes PLACING marca FROM 1 FOR 6);
  bytes := set_byte(bytes, 6, (b'0111' || get_byte(bytes, 6)::bit(4))::bit(8)::int);
  RETURN encode(bytes, 'hex')::uuid;
END
$$ LANGUAGE plpgsql VOLATILE;

CREATE FUNCTION fijar_actualizado_en() RETURNS trigger AS $$
BEGIN
  NEW.actualizado_en := now();
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- Acceso y usuarios

CREATE TABLE usuario (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid,
  rol text NOT NULL,
  username text NOT NULL,
  password_hash text NOT NULL,
  nombres text,
  apellidos text,
  tipo_documento text,
  numero_documento text,
  correo text,
  celular text,
  estado text NOT NULL DEFAULT 'activa',
  contrasena_inicial boolean NOT NULL DEFAULT true,
  intentos_fallidos smallint NOT NULL DEFAULT 0,
  bloqueado_hasta timestamptz,
  token_version integer NOT NULL DEFAULT 0,
  ultimo_ingreso timestamptz,
  politica_version text,
  politica_aceptada_en timestamptz,
  tutorial_completado boolean NOT NULL DEFAULT false,
  buzon_recibos text,
  horas_recordatorio smallint NOT NULL DEFAULT 4,
  silencio_desde time,
  silencio_hasta time,
  resumen_diario_hora time,
  reporte_mensual_activo boolean NOT NULL DEFAULT false,
  eliminado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_usuario PRIMARY KEY (id),
  CONSTRAINT fk_usuario_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT uq_usuario_numero_documento UNIQUE (numero_documento),
  CONSTRAINT uq_usuario_buzon_recibos UNIQUE (buzon_recibos),
  CONSTRAINT ck_usuario_rol CHECK (rol IN ('gerente', 'asistente')),
  CONSTRAINT ck_usuario_rol_gerente CHECK ((rol = 'gerente') = (gerente_id IS NULL)),
  CONSTRAINT ck_usuario_estado CHECK (estado IN ('activa', 'inactiva')),
  CONSTRAINT ck_usuario_username CHECK (char_length(username) BETWEEN 3 AND 30),
  CONSTRAINT ck_usuario_tipo_documento CHECK (tipo_documento IN ('dni', 'ce', 'pasaporte')),
  CONSTRAINT ck_usuario_numero_documento CHECK (
    (tipo_documento = 'dni' AND numero_documento ~ '^[0-9]{8}$')
    OR (tipo_documento IN ('ce', 'pasaporte') AND numero_documento ~ '^[A-Za-z0-9]{9,12}$')
    OR (tipo_documento IS NULL AND numero_documento IS NULL)
  ),
  CONSTRAINT ck_usuario_celular CHECK (celular ~ '^9[0-9]{8}$'),
  CONSTRAINT ck_usuario_intentos_fallidos CHECK (intentos_fallidos >= 0),
  CONSTRAINT ck_usuario_horas_recordatorio CHECK (horas_recordatorio BETWEEN 1 AND 24)
);
CREATE INDEX ix_usuario_gerente_id ON usuario (gerente_id);
CREATE UNIQUE INDEX uq_usuario_username ON usuario (lower(username));
CREATE UNIQUE INDEX uq_usuario_correo ON usuario (lower(correo));
CREATE UNIQUE INDEX uq_usuario_asistente_activa ON usuario (gerente_id)
  WHERE rol = 'asistente' AND estado = 'activa' AND eliminado_en IS NULL;
CREATE TRIGGER tg_usuario_actualizado_en BEFORE UPDATE ON usuario
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE historial_contrasena (
  id uuid DEFAULT uuid_generate_v7(),
  usuario_id uuid NOT NULL,
  password_hash text NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_historial_contrasena PRIMARY KEY (id),
  CONSTRAINT fk_historial_contrasena_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE CASCADE
);
CREATE INDEX ix_historial_contrasena_usuario_id ON historial_contrasena (usuario_id);

CREATE TABLE cambio_usuario (
  id uuid DEFAULT uuid_generate_v7(),
  usuario_id uuid NOT NULL,
  anterior text NOT NULL,
  nuevo text NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_cambio_usuario PRIMARY KEY (id),
  CONSTRAINT fk_cambio_usuario_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE CASCADE
);
CREATE INDEX ix_cambio_usuario_usuario_id ON cambio_usuario (usuario_id);

CREATE TABLE token_restablecimiento (
  id uuid DEFAULT uuid_generate_v7(),
  usuario_id uuid NOT NULL,
  token_hash text NOT NULL,
  expira_en timestamptz NOT NULL,
  usado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_token_restablecimiento PRIMARY KEY (id),
  CONSTRAINT fk_token_restablecimiento_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE CASCADE,
  CONSTRAINT uq_token_restablecimiento_token_hash UNIQUE (token_hash)
);
CREATE INDEX ix_token_restablecimiento_usuario_id ON token_restablecimiento (usuario_id);

CREATE TABLE activacion_cuenta (
  id uuid DEFAULT uuid_generate_v7(),
  cuenta_id uuid NOT NULL,
  accion text NOT NULL,
  realizada_por uuid NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_activacion_cuenta PRIMARY KEY (id),
  CONSTRAINT fk_activacion_cuenta_cuenta_id_usuario FOREIGN KEY (cuenta_id) REFERENCES usuario (id),
  CONSTRAINT fk_activacion_cuenta_realizada_por_usuario FOREIGN KEY (realizada_por)
    REFERENCES usuario (id),
  CONSTRAINT ck_activacion_cuenta_accion CHECK (accion IN ('activada', 'desactivada', 'eliminada'))
);
CREATE INDEX ix_activacion_cuenta_cuenta_id ON activacion_cuenta (cuenta_id);
CREATE INDEX ix_activacion_cuenta_realizada_por ON activacion_cuenta (realizada_por);

CREATE TABLE auditoria (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  usuario_id uuid,
  usuario_nombre text NOT NULL,
  accion text NOT NULL,
  entidad text NOT NULL,
  entidad_id uuid,
  detalle jsonb NOT NULL DEFAULT '{}'::jsonb,
  dispositivo text,
  ip inet,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_auditoria PRIMARY KEY (id),
  CONSTRAINT fk_auditoria_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_auditoria_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE SET NULL
);
CREATE INDEX ix_auditoria_gerente_id_creado_en ON auditoria (gerente_id, creado_en);
CREATE INDEX ix_auditoria_usuario_id ON auditoria (usuario_id);

-- Configuración del gerente

CREATE TABLE medio_pago (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  tipo text NOT NULL,
  alias text NOT NULL,
  banco text,
  marca text,
  ultimos4 text,
  vencimiento_mes smallint,
  vencimiento_anio smallint,
  moneda text NOT NULL DEFAULT 'PEN',
  celular text,
  token_pasarela text,
  principal boolean NOT NULL DEFAULT false,
  estado text NOT NULL DEFAULT 'activo',
  eliminado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_medio_pago PRIMARY KEY (id),
  CONSTRAINT fk_medio_pago_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT ck_medio_pago_tipo CHECK (
    tipo IN ('tarjeta_credito', 'tarjeta_debito', 'cuenta_bancaria', 'billetera')
  ),
  CONSTRAINT ck_medio_pago_ultimos4 CHECK (ultimos4 ~ '^[0-9]{4}$'),
  CONSTRAINT ck_medio_pago_vencimiento_mes CHECK (vencimiento_mes BETWEEN 1 AND 12),
  CONSTRAINT ck_medio_pago_moneda CHECK (moneda IN ('PEN', 'USD')),
  CONSTRAINT ck_medio_pago_celular CHECK (celular ~ '^9[0-9]{8}$'),
  CONSTRAINT ck_medio_pago_estado CHECK (estado IN ('activo', 'desactivado'))
);
CREATE INDEX ix_medio_pago_gerente_id ON medio_pago (gerente_id);
CREATE UNIQUE INDEX uq_medio_pago_alias ON medio_pago (gerente_id, lower(alias))
  WHERE eliminado_en IS NULL;
CREATE UNIQUE INDEX uq_medio_pago_principal ON medio_pago (gerente_id)
  WHERE principal AND eliminado_en IS NULL;
CREATE TRIGGER tg_medio_pago_actualizado_en BEFORE UPDATE ON medio_pago
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE limite (
  gerente_id uuid NOT NULL,
  por_pago numeric(12,2),
  mensual numeric(12,2),
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_limite PRIMARY KEY (gerente_id),
  CONSTRAINT fk_limite_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT ck_limite_por_pago CHECK (por_pago > 0),
  CONSTRAINT ck_limite_mensual CHECK (mensual > 0),
  CONSTRAINT ck_limite_por_pago_mensual CHECK (por_pago <= mensual)
);
CREATE TRIGGER tg_limite_actualizado_en BEFORE UPDATE ON limite
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE configuracion_ia (
  gerente_id uuid NOT NULL,
  proveedor text NOT NULL DEFAULT 'incluida',
  api_key_cifrada bytea,
  url_modelo text,
  respaldo_activo boolean NOT NULL DEFAULT true,
  estado text NOT NULL DEFAULT 'sin_configurar',
  ultimo_error text,
  ultima_prueba_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_configuracion_ia PRIMARY KEY (gerente_id),
  CONSTRAINT fk_configuracion_ia_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT ck_configuracion_ia_proveedor CHECK (
    proveedor IN ('incluida', 'anthropic', 'openai', 'propio')
  ),
  CONSTRAINT ck_configuracion_ia_estado CHECK (
    estado IN ('conectada', 'con_error', 'sin_configurar')
  )
);
CREATE TRIGGER tg_configuracion_ia_actualizado_en BEFORE UPDATE ON configuracion_ia
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

-- Catálogos

CREATE TABLE ubigeo (
  codigo text NOT NULL,
  departamento text NOT NULL,
  provincia text NOT NULL,
  distrito text NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_ubigeo PRIMARY KEY (codigo),
  CONSTRAINT ck_ubigeo_codigo CHECK (codigo ~ '^[0-9]{6}$')
);

CREATE TABLE inmueble (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  nombre text NOT NULL,
  ubigeo text NOT NULL,
  direccion text,
  eliminado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_inmueble PRIMARY KEY (id),
  CONSTRAINT fk_inmueble_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_inmueble_ubigeo_ubigeo FOREIGN KEY (ubigeo) REFERENCES ubigeo (codigo)
);
CREATE INDEX ix_inmueble_gerente_id ON inmueble (gerente_id);
CREATE INDEX ix_inmueble_ubigeo ON inmueble (ubigeo);
CREATE UNIQUE INDEX uq_inmueble_nombre ON inmueble (gerente_id, lower(nombre))
  WHERE eliminado_en IS NULL;
CREATE TRIGGER tg_inmueble_actualizado_en BEFORE UPDATE ON inmueble
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE empresa (
  id uuid DEFAULT uuid_generate_v7(),
  nombre text NOT NULL,
  ruc text,
  tipo_servicio text NOT NULL,
  patron_codigo text,
  url_portal text,
  tiene_robot boolean NOT NULL DEFAULT false,
  robot_activo boolean NOT NULL DEFAULT false,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_empresa PRIMARY KEY (id),
  CONSTRAINT uq_empresa_ruc UNIQUE (ruc),
  CONSTRAINT ck_empresa_ruc CHECK (ruc ~ '^[0-9]{11}$'),
  CONSTRAINT ck_empresa_tipo_servicio CHECK (
    tipo_servicio IN ('luz', 'agua', 'gas', 'telecomunicaciones', 'otro')
  )
);
CREATE TRIGGER tg_empresa_actualizado_en BEFORE UPDATE ON empresa
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE empresa_zona (
  empresa_id uuid NOT NULL,
  ubigeo text NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_empresa_zona PRIMARY KEY (empresa_id, ubigeo),
  CONSTRAINT fk_empresa_zona_empresa_id_empresa FOREIGN KEY (empresa_id)
    REFERENCES empresa (id) ON DELETE CASCADE,
  CONSTRAINT fk_empresa_zona_ubigeo_ubigeo FOREIGN KEY (ubigeo) REFERENCES ubigeo (codigo)
);
CREATE INDEX ix_empresa_zona_ubigeo ON empresa_zona (ubigeo);

CREATE TABLE canal_pago (
  id uuid DEFAULT uuid_generate_v7(),
  empresa_id uuid NOT NULL,
  lugar_pago text NOT NULL,
  comision numeric(12,2) NOT NULL DEFAULT 0,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_canal_pago PRIMARY KEY (id),
  CONSTRAINT fk_canal_pago_empresa_id_empresa FOREIGN KEY (empresa_id)
    REFERENCES empresa (id) ON DELETE CASCADE,
  CONSTRAINT uq_canal_pago_empresa_id_lugar_pago UNIQUE (empresa_id, lugar_pago),
  CONSTRAINT ck_canal_pago_lugar_pago CHECK (
    lugar_pago IN ('agente_bcp', 'agente_kasnet', 'ventanilla_empresa', 'banca_movil', 'otro')
  ),
  CONSTRAINT ck_canal_pago_comision CHECK (comision >= 0)
);
CREATE TRIGGER tg_canal_pago_actualizado_en BEFORE UPDATE ON canal_pago
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();
