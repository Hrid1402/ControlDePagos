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

-- Servicios y deudas

CREATE TABLE categoria (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  nombre text NOT NULL,
  color text NOT NULL DEFAULT '#64748B',
  icono text NOT NULL DEFAULT 'pi-tag',
  tipo text NOT NULL,
  precargada boolean NOT NULL DEFAULT false,
  creado_por uuid,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_categoria PRIMARY KEY (id),
  CONSTRAINT fk_categoria_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_categoria_creado_por_usuario FOREIGN KEY (creado_por) REFERENCES usuario (id),
  CONSTRAINT ck_categoria_nombre CHECK (char_length(nombre) BETWEEN 1 AND 40),
  CONSTRAINT ck_categoria_color CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
  CONSTRAINT ck_categoria_tipo CHECK (
    tipo IN ('servicio_variable', 'monto_fijo', 'tarjeta', 'prestamo')
  )
);
CREATE INDEX ix_categoria_gerente_id ON categoria (gerente_id);
CREATE INDEX ix_categoria_creado_por ON categoria (creado_por);
CREATE UNIQUE INDEX uq_categoria_nombre ON categoria (gerente_id, lower(nombre));
CREATE TRIGGER tg_categoria_actualizado_en BEFORE UPDATE ON categoria
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE servicio (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  categoria_id uuid NOT NULL,
  inmueble_id uuid,
  empresa_id uuid,
  empresa_nombre text,
  codigo_suministro text NOT NULL,
  titular text,
  alias text,
  lugar_pago text,
  notas text,
  medio_pago_id uuid,
  portal_usuario_cifrado bytea,
  portal_clave_cifrada bytea,
  estado text NOT NULL DEFAULT 'activo',
  creado_por uuid,
  eliminado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_servicio PRIMARY KEY (id),
  CONSTRAINT fk_servicio_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_servicio_categoria_id_categoria FOREIGN KEY (categoria_id)
    REFERENCES categoria (id),
  CONSTRAINT fk_servicio_inmueble_id_inmueble FOREIGN KEY (inmueble_id)
    REFERENCES inmueble (id) ON DELETE SET NULL,
  CONSTRAINT fk_servicio_empresa_id_empresa FOREIGN KEY (empresa_id) REFERENCES empresa (id),
  CONSTRAINT fk_servicio_medio_pago_id_medio_pago FOREIGN KEY (medio_pago_id)
    REFERENCES medio_pago (id) ON DELETE SET NULL,
  CONSTRAINT fk_servicio_creado_por_usuario FOREIGN KEY (creado_por) REFERENCES usuario (id),
  CONSTRAINT ck_servicio_empresa CHECK (empresa_id IS NOT NULL OR empresa_nombre IS NOT NULL),
  CONSTRAINT ck_servicio_lugar_pago CHECK (
    lugar_pago IN ('agente_bcp', 'agente_kasnet', 'ventanilla_empresa', 'banca_movil', 'otro')
  ),
  CONSTRAINT ck_servicio_notas CHECK (char_length(notas) <= 500),
  CONSTRAINT ck_servicio_estado CHECK (estado IN ('activo', 'baja'))
);
CREATE INDEX ix_servicio_gerente_id ON servicio (gerente_id);
CREATE INDEX ix_servicio_categoria_id ON servicio (categoria_id);
CREATE INDEX ix_servicio_inmueble_id ON servicio (inmueble_id);
CREATE INDEX ix_servicio_empresa_id ON servicio (empresa_id);
CREATE INDEX ix_servicio_medio_pago_id ON servicio (medio_pago_id);
CREATE INDEX ix_servicio_creado_por ON servicio (creado_por);
CREATE UNIQUE INDEX uq_servicio_codigo ON servicio (
  gerente_id, coalesce(empresa_id::text, lower(empresa_nombre)), codigo_suministro
) WHERE eliminado_en IS NULL;
CREATE TRIGGER tg_servicio_actualizado_en BEFORE UPDATE ON servicio
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE recurrencia (
  id uuid DEFAULT uuid_generate_v7(),
  servicio_id uuid NOT NULL,
  tipo text NOT NULL,
  monto numeric(12,2),
  moneda text NOT NULL DEFAULT 'PEN',
  dia_emision smallint,
  dia_vencimiento smallint NOT NULL,
  activa boolean NOT NULL DEFAULT true,
  ultima_generacion date,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_recurrencia PRIMARY KEY (id),
  CONSTRAINT fk_recurrencia_servicio_id_servicio FOREIGN KEY (servicio_id)
    REFERENCES servicio (id) ON DELETE CASCADE,
  CONSTRAINT uq_recurrencia_servicio_id UNIQUE (servicio_id),
  CONSTRAINT ck_recurrencia_tipo CHECK (tipo IN ('monto_fijo', 'variable')),
  CONSTRAINT ck_recurrencia_monto CHECK (monto > 0),
  CONSTRAINT ck_recurrencia_monto_fijo CHECK (tipo = 'variable' OR monto IS NOT NULL),
  CONSTRAINT ck_recurrencia_moneda CHECK (moneda IN ('PEN', 'USD')),
  CONSTRAINT ck_recurrencia_dia_emision CHECK (dia_emision BETWEEN 1 AND 31),
  CONSTRAINT ck_recurrencia_dia_vencimiento CHECK (dia_vencimiento BETWEEN 1 AND 31)
);
CREATE TRIGGER tg_recurrencia_actualizado_en BEFORE UPDATE ON recurrencia
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE prestamo (
  id uuid DEFAULT uuid_generate_v7(),
  servicio_id uuid NOT NULL,
  monto_total numeric(12,2) NOT NULL,
  cuotas_total smallint NOT NULL,
  monto_cuota numeric(12,2) NOT NULL,
  fecha_primera_cuota date NOT NULL,
  moneda text NOT NULL DEFAULT 'PEN',
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_prestamo PRIMARY KEY (id),
  CONSTRAINT fk_prestamo_servicio_id_servicio FOREIGN KEY (servicio_id) REFERENCES servicio (id),
  CONSTRAINT ck_prestamo_monto_total CHECK (monto_total > 0),
  CONSTRAINT ck_prestamo_cuotas_total CHECK (cuotas_total > 0),
  CONSTRAINT ck_prestamo_monto_cuota CHECK (monto_cuota > 0),
  CONSTRAINT ck_prestamo_moneda CHECK (moneda IN ('PEN', 'USD'))
);
CREATE INDEX ix_prestamo_servicio_id ON prestamo (servicio_id);
CREATE TRIGGER tg_prestamo_actualizado_en BEFORE UPDATE ON prestamo
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE deuda (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  servicio_id uuid NOT NULL,
  prestamo_id uuid,
  cuota_numero smallint,
  periodo date NOT NULL,
  monto numeric(12,2) NOT NULL,
  moneda text NOT NULL DEFAULT 'PEN',
  fecha_emision date,
  fecha_vencimiento date NOT NULL,
  fecha_estimada date,
  numero_recibo text,
  recibo_url text,
  estado text NOT NULL DEFAULT 'pendiente',
  origen text NOT NULL DEFAULT 'manual',
  fecha_corte date,
  pago_minimo numeric(12,2),
  pago_total numeric(12,2),
  fijada boolean NOT NULL DEFAULT false,
  oculta_hasta timestamptz,
  pago_iniciado_en timestamptz,
  pago_iniciado_por uuid,
  pago_realizado boolean NOT NULL DEFAULT false,
  recordatorios_enviados smallint NOT NULL DEFAULT 0,
  pagada_fuera_en timestamptz,
  creado_por uuid,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_deuda PRIMARY KEY (id),
  CONSTRAINT fk_deuda_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_deuda_servicio_id_servicio FOREIGN KEY (servicio_id) REFERENCES servicio (id),
  CONSTRAINT fk_deuda_prestamo_id_prestamo FOREIGN KEY (prestamo_id) REFERENCES prestamo (id),
  CONSTRAINT fk_deuda_pago_iniciado_por_usuario FOREIGN KEY (pago_iniciado_por)
    REFERENCES usuario (id),
  CONSTRAINT fk_deuda_creado_por_usuario FOREIGN KEY (creado_por) REFERENCES usuario (id),
  CONSTRAINT ck_deuda_periodo CHECK (extract(day FROM periodo) = 1),
  CONSTRAINT ck_deuda_monto CHECK (monto > 0),
  CONSTRAINT ck_deuda_moneda CHECK (moneda IN ('PEN', 'USD')),
  CONSTRAINT ck_deuda_estado CHECK (
    estado IN (
      'esperando_recibo', 'pendiente', 'esperando_aprobacion', 'en_proceso', 'por_validar',
      'pagada_parcial', 'pagada', 'con_problema', 'anulada'
    )
  ),
  CONSTRAINT ck_deuda_origen CHECK (origen IN ('manual', 'recurrente', 'robot', 'ia')),
  CONSTRAINT ck_deuda_cuota CHECK ((prestamo_id IS NULL) = (cuota_numero IS NULL)),
  CONSTRAINT ck_deuda_cuota_numero CHECK (cuota_numero > 0),
  CONSTRAINT ck_deuda_pago_minimo CHECK (pago_minimo > 0),
  CONSTRAINT ck_deuda_pago_total CHECK (pago_total > 0),
  CONSTRAINT ck_deuda_recordatorios_enviados CHECK (recordatorios_enviados >= 0)
);
CREATE INDEX ix_deuda_gerente_id_estado ON deuda (gerente_id, estado);
CREATE INDEX ix_deuda_gerente_id_fecha_vencimiento ON deuda (gerente_id, fecha_vencimiento);
CREATE INDEX ix_deuda_servicio_id ON deuda (servicio_id);
CREATE INDEX ix_deuda_prestamo_id ON deuda (prestamo_id);
CREATE INDEX ix_deuda_pago_iniciado_por ON deuda (pago_iniciado_por);
CREATE INDEX ix_deuda_creado_por ON deuda (creado_por);
CREATE UNIQUE INDEX uq_deuda_periodo ON deuda (servicio_id, periodo, coalesce(cuota_numero, 0))
  WHERE estado <> 'anulada';
CREATE TRIGGER tg_deuda_actualizado_en BEFORE UPDATE ON deuda
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE historial_monto (
  id uuid DEFAULT uuid_generate_v7(),
  deuda_id uuid NOT NULL,
  monto_anterior numeric(12,2) NOT NULL,
  monto_nuevo numeric(12,2) NOT NULL,
  origen text NOT NULL,
  usuario_id uuid,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_historial_monto PRIMARY KEY (id),
  CONSTRAINT fk_historial_monto_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE CASCADE,
  CONSTRAINT fk_historial_monto_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id),
  CONSTRAINT ck_historial_monto_origen CHECK (origen IN ('manual', 'robot'))
);
CREATE INDEX ix_historial_monto_deuda_id ON historial_monto (deuda_id);
CREATE INDEX ix_historial_monto_usuario_id ON historial_monto (usuario_id);

CREATE TABLE comentario (
  id uuid DEFAULT uuid_generate_v7(),
  deuda_id uuid NOT NULL,
  usuario_id uuid NOT NULL,
  tipo text NOT NULL DEFAULT 'texto',
  texto text NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_comentario PRIMARY KEY (id),
  CONSTRAINT fk_comentario_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE CASCADE,
  CONSTRAINT fk_comentario_usuario_id_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id),
  CONSTRAINT ck_comentario_tipo CHECK (tipo IN ('texto', 'respuesta_rapida')),
  CONSTRAINT ck_comentario_texto CHECK (char_length(texto) BETWEEN 1 AND 500)
);
CREATE INDEX ix_comentario_deuda_id ON comentario (deuda_id);
CREATE INDEX ix_comentario_usuario_id ON comentario (usuario_id);

CREATE TABLE regla_alerta (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  tipo text NOT NULL DEFAULT 'vencimiento',
  alcance text NOT NULL DEFAULT 'general',
  categoria_id uuid,
  servicio_id uuid,
  dias_antes smallint[] NOT NULL DEFAULT '{3}',
  porcentaje_aumento numeric(5,2),
  canales text[] NOT NULL DEFAULT '{app}',
  destinatario text NOT NULL DEFAULT 'gerente',
  hora_envio time NOT NULL DEFAULT '08:00',
  activa boolean NOT NULL DEFAULT true,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_regla_alerta PRIMARY KEY (id),
  CONSTRAINT fk_regla_alerta_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_regla_alerta_categoria_id_categoria FOREIGN KEY (categoria_id)
    REFERENCES categoria (id) ON DELETE CASCADE,
  CONSTRAINT fk_regla_alerta_servicio_id_servicio FOREIGN KEY (servicio_id)
    REFERENCES servicio (id) ON DELETE CASCADE,
  CONSTRAINT ck_regla_alerta_tipo CHECK (tipo IN ('vencimiento', 'consumo_anormal')),
  CONSTRAINT ck_regla_alerta_alcance CHECK (alcance IN ('general', 'categoria', 'servicio')),
  CONSTRAINT ck_regla_alerta_alcance_destino CHECK (
    (alcance = 'general' AND categoria_id IS NULL AND servicio_id IS NULL)
    OR (alcance = 'categoria' AND categoria_id IS NOT NULL AND servicio_id IS NULL)
    OR (alcance = 'servicio' AND servicio_id IS NOT NULL AND categoria_id IS NULL)
  ),
  CONSTRAINT ck_regla_alerta_dias_antes CHECK (
    cardinality(dias_antes) > 0 AND 1 <= ALL (dias_antes) AND 30 >= ALL (dias_antes)
  ),
  CONSTRAINT ck_regla_alerta_porcentaje_aumento CHECK (
    (tipo = 'consumo_anormal') = (porcentaje_aumento IS NOT NULL) AND porcentaje_aumento > 0
    OR (tipo = 'vencimiento' AND porcentaje_aumento IS NULL)
  ),
  CONSTRAINT ck_regla_alerta_canales CHECK (
    cardinality(canales) > 0 AND canales <@ ARRAY['app', 'correo', 'whatsapp']
  ),
  CONSTRAINT ck_regla_alerta_destinatario CHECK (
    destinatario IN ('gerente', 'asistente', 'ambos')
  ),
  CONSTRAINT ck_regla_alerta_hora_envio CHECK (hora_envio BETWEEN '06:00' AND '22:00')
);
CREATE INDEX ix_regla_alerta_gerente_id ON regla_alerta (gerente_id);
CREATE INDEX ix_regla_alerta_categoria_id ON regla_alerta (categoria_id);
CREATE INDEX ix_regla_alerta_servicio_id ON regla_alerta (servicio_id);
CREATE TRIGGER tg_regla_alerta_actualizado_en BEFORE UPDATE ON regla_alerta
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

-- Pagos

CREATE TABLE orden_pago (
  id uuid DEFAULT uuid_generate_v7(),
  deuda_id uuid NOT NULL,
  gerente_id uuid NOT NULL,
  asistente_id uuid,
  plazo timestamptz,
  mensaje text,
  estado text NOT NULL DEFAULT 'enviada',
  motivo_rechazo text,
  reenvios smallint NOT NULL DEFAULT 0,
  vista_en timestamptz,
  aceptada_en timestamptz,
  pagada_en timestamptz,
  cancelada_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_orden_pago PRIMARY KEY (id),
  CONSTRAINT fk_orden_pago_deuda_id_deuda FOREIGN KEY (deuda_id) REFERENCES deuda (id),
  CONSTRAINT fk_orden_pago_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_orden_pago_asistente_id_usuario FOREIGN KEY (asistente_id)
    REFERENCES usuario (id),
  CONSTRAINT ck_orden_pago_mensaje CHECK (char_length(mensaje) <= 300),
  CONSTRAINT ck_orden_pago_estado CHECK (
    estado IN ('enviada', 'vista', 'aceptada', 'rechazada', 'pagada', 'cancelada')
  ),
  CONSTRAINT ck_orden_pago_reenvios CHECK (reenvios >= 0)
);
CREATE INDEX ix_orden_pago_deuda_id ON orden_pago (deuda_id);
CREATE INDEX ix_orden_pago_gerente_id ON orden_pago (gerente_id);
CREATE INDEX ix_orden_pago_asistente_id ON orden_pago (asistente_id);
CREATE UNIQUE INDEX uq_orden_pago_abierta ON orden_pago (deuda_id)
  WHERE estado IN ('enviada', 'vista', 'aceptada');
CREATE TRIGGER tg_orden_pago_actualizado_en BEFORE UPDATE ON orden_pago
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE reporte_problema (
  id uuid DEFAULT uuid_generate_v7(),
  deuda_id uuid NOT NULL,
  orden_id uuid,
  usuario_id uuid NOT NULL,
  motivo text NOT NULL,
  detalle text,
  resolucion text,
  resuelto_por uuid,
  resuelto_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_reporte_problema PRIMARY KEY (id),
  CONSTRAINT fk_reporte_problema_deuda_id_deuda FOREIGN KEY (deuda_id) REFERENCES deuda (id),
  CONSTRAINT fk_reporte_problema_orden_id_orden_pago FOREIGN KEY (orden_id)
    REFERENCES orden_pago (id),
  CONSTRAINT fk_reporte_problema_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id),
  CONSTRAINT fk_reporte_problema_resuelto_por_usuario FOREIGN KEY (resuelto_por)
    REFERENCES usuario (id),
  CONSTRAINT ck_reporte_problema_motivo CHECK (
    motivo IN (
      'portal_caido', 'saldo_insuficiente', 'monto_distinto', 'agente_cerrado', 'otro_medio',
      'otro'
    )
  ),
  CONSTRAINT ck_reporte_problema_detalle CHECK (motivo <> 'otro' OR detalle IS NOT NULL),
  CONSTRAINT ck_reporte_problema_resolucion CHECK (
    resolucion IN ('reintentar', 'cambiar_medio', 'pago_gerente')
  )
);
CREATE INDEX ix_reporte_problema_deuda_id ON reporte_problema (deuda_id);
CREATE INDEX ix_reporte_problema_orden_id ON reporte_problema (orden_id);
CREATE INDEX ix_reporte_problema_usuario_id ON reporte_problema (usuario_id);
CREATE INDEX ix_reporte_problema_resuelto_por ON reporte_problema (resuelto_por);
CREATE TRIGGER tg_reporte_problema_actualizado_en BEFORE UPDATE ON reporte_problema
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE pago (
  id uuid DEFAULT uuid_generate_v7(),
  deuda_id uuid NOT NULL,
  medio_pago_id uuid NOT NULL,
  usuario_id uuid NOT NULL,
  monto numeric(12,2) NOT NULL,
  moneda text NOT NULL DEFAULT 'PEN',
  comision numeric(12,2) NOT NULL DEFAULT 0,
  estado text NOT NULL DEFAULT 'iniciado',
  referencia_externa text,
  motivo_error text,
  constancia_url text,
  completado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_pago PRIMARY KEY (id),
  CONSTRAINT fk_pago_deuda_id_deuda FOREIGN KEY (deuda_id) REFERENCES deuda (id),
  CONSTRAINT fk_pago_medio_pago_id_medio_pago FOREIGN KEY (medio_pago_id)
    REFERENCES medio_pago (id),
  CONSTRAINT fk_pago_usuario_id_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id),
  CONSTRAINT ck_pago_monto CHECK (monto > 0),
  CONSTRAINT ck_pago_moneda CHECK (moneda IN ('PEN', 'USD')),
  CONSTRAINT ck_pago_comision CHECK (comision >= 0),
  CONSTRAINT ck_pago_estado CHECK (
    estado IN ('iniciado', 'esperando_confirmacion', 'confirmado', 'rechazado', 'incierto')
  )
);
CREATE INDEX ix_pago_deuda_id ON pago (deuda_id);
CREATE INDEX ix_pago_medio_pago_id ON pago (medio_pago_id);
CREATE INDEX ix_pago_usuario_id ON pago (usuario_id);
CREATE UNIQUE INDEX uq_pago_en_curso ON pago (deuda_id)
  WHERE estado IN ('iniciado', 'esperando_confirmacion', 'incierto');
CREATE TRIGGER tg_pago_actualizado_en BEFORE UPDATE ON pago
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE solicitud_aprobacion (
  id uuid DEFAULT uuid_generate_v7(),
  deuda_id uuid NOT NULL,
  asistente_id uuid NOT NULL,
  monto numeric(12,2) NOT NULL,
  estado text NOT NULL DEFAULT 'pendiente',
  motivo text,
  recordatorios_enviados smallint NOT NULL DEFAULT 0,
  resuelta_por uuid,
  resuelta_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_solicitud_aprobacion PRIMARY KEY (id),
  CONSTRAINT fk_solicitud_aprobacion_deuda_id_deuda FOREIGN KEY (deuda_id) REFERENCES deuda (id),
  CONSTRAINT fk_solicitud_aprobacion_asistente_id_usuario FOREIGN KEY (asistente_id)
    REFERENCES usuario (id),
  CONSTRAINT fk_solicitud_aprobacion_resuelta_por_usuario FOREIGN KEY (resuelta_por)
    REFERENCES usuario (id),
  CONSTRAINT ck_solicitud_aprobacion_monto CHECK (monto > 0),
  CONSTRAINT ck_solicitud_aprobacion_estado CHECK (
    estado IN ('pendiente', 'aprobada', 'rechazada')
  ),
  CONSTRAINT ck_solicitud_aprobacion_recordatorios CHECK (recordatorios_enviados >= 0)
);
CREATE INDEX ix_solicitud_aprobacion_deuda_id ON solicitud_aprobacion (deuda_id);
CREATE INDEX ix_solicitud_aprobacion_asistente_id ON solicitud_aprobacion (asistente_id);
CREATE INDEX ix_solicitud_aprobacion_resuelta_por ON solicitud_aprobacion (resuelta_por);
CREATE UNIQUE INDEX uq_solicitud_aprobacion_pendiente ON solicitud_aprobacion (deuda_id)
  WHERE estado = 'pendiente';
CREATE TRIGGER tg_solicitud_aprobacion_actualizado_en BEFORE UPDATE ON solicitud_aprobacion
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

-- Comprobantes y recibos

CREATE TABLE comprobante (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  archivo_url text NOT NULL,
  archivo_tipo text NOT NULL,
  archivo_bytes integer NOT NULL,
  hash_sha256 text NOT NULL,
  entidad text,
  numero_operacion text,
  monto numeric(12,2),
  moneda text NOT NULL DEFAULT 'PEN',
  fecha_pago timestamptz,
  texto_ocr text,
  confianza numeric(4,3),
  datos_extraidos jsonb NOT NULL DEFAULT '{}'::jsonb,
  estado text NOT NULL DEFAULT 'procesando',
  motivo_codigo text,
  deuda_sugerida_id uuid,
  fondos text NOT NULL DEFAULT 'gerente',
  reemplaza_a_id uuid,
  subido_por uuid NOT NULL,
  revisado_por uuid,
  revisado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_comprobante PRIMARY KEY (id),
  CONSTRAINT fk_comprobante_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_comprobante_deuda_sugerida_id_deuda FOREIGN KEY (deuda_sugerida_id)
    REFERENCES deuda (id) ON DELETE SET NULL,
  CONSTRAINT fk_comprobante_reemplaza_a_id_comprobante FOREIGN KEY (reemplaza_a_id)
    REFERENCES comprobante (id),
  CONSTRAINT fk_comprobante_subido_por_usuario FOREIGN KEY (subido_por) REFERENCES usuario (id),
  CONSTRAINT fk_comprobante_revisado_por_usuario FOREIGN KEY (revisado_por)
    REFERENCES usuario (id),
  CONSTRAINT ck_comprobante_archivo_tipo CHECK (archivo_tipo IN ('jpg', 'png', 'pdf')),
  CONSTRAINT ck_comprobante_archivo_bytes CHECK (archivo_bytes BETWEEN 1 AND 10485760),
  CONSTRAINT ck_comprobante_hash_sha256 CHECK (hash_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_comprobante_entidad CHECK (
    entidad IN (
      'bcp', 'interbank', 'bbva', 'scotiabank', 'yape', 'plin', 'agente_bcp', 'kasnet', 'otra'
    )
  ),
  CONSTRAINT ck_comprobante_monto CHECK (monto > 0),
  CONSTRAINT ck_comprobante_moneda CHECK (moneda IN ('PEN', 'USD')),
  CONSTRAINT ck_comprobante_confianza CHECK (confianza BETWEEN 0 AND 1),
  CONSTRAINT ck_comprobante_estado CHECK (
    estado IN ('procesando', 'validado', 'por_confirmar', 'en_revision', 'rechazado')
  ),
  CONSTRAINT ck_comprobante_motivo_codigo CHECK (
    motivo_codigo IN (
      'duplicado', 'ilegible', 'otra_deuda', 'monto_menor', 'monto_mayor', 'fecha_dudosa',
      'baja_confianza'
    )
  ),
  CONSTRAINT ck_comprobante_fondos CHECK (fondos IN ('gerente', 'caja_chica', 'dinero_propio'))
);
CREATE INDEX ix_comprobante_gerente_id_estado ON comprobante (gerente_id, estado);
CREATE INDEX ix_comprobante_deuda_sugerida_id ON comprobante (deuda_sugerida_id);
CREATE INDEX ix_comprobante_reemplaza_a_id ON comprobante (reemplaza_a_id);
CREATE INDEX ix_comprobante_subido_por ON comprobante (subido_por);
CREATE INDEX ix_comprobante_revisado_por ON comprobante (revisado_por);
CREATE UNIQUE INDEX uq_comprobante_hash ON comprobante (hash_sha256)
  WHERE estado <> 'rechazado';
CREATE UNIQUE INDEX uq_comprobante_operacion ON comprobante (entidad, numero_operacion)
  WHERE numero_operacion IS NOT NULL AND estado <> 'rechazado';
CREATE TRIGGER tg_comprobante_actualizado_en BEFORE UPDATE ON comprobante
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE comprobante_deuda (
  comprobante_id uuid NOT NULL,
  deuda_id uuid NOT NULL,
  monto_aplicado numeric(12,2) NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_comprobante_deuda PRIMARY KEY (comprobante_id, deuda_id),
  CONSTRAINT fk_comprobante_deuda_comprobante_id_comprobante FOREIGN KEY (comprobante_id)
    REFERENCES comprobante (id) ON DELETE CASCADE,
  CONSTRAINT fk_comprobante_deuda_deuda_id_deuda FOREIGN KEY (deuda_id) REFERENCES deuda (id),
  CONSTRAINT ck_comprobante_deuda_monto_aplicado CHECK (monto_aplicado > 0)
);
CREATE INDEX ix_comprobante_deuda_deuda_id ON comprobante_deuda (deuda_id);

CREATE TABLE recibo (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  archivo_url text NOT NULL,
  archivo_tipo text NOT NULL,
  hash_sha256 text NOT NULL,
  pagina smallint NOT NULL DEFAULT 1,
  origen text NOT NULL,
  estado text NOT NULL DEFAULT 'procesando',
  proveedor_ia text,
  datos_extraidos jsonb NOT NULL DEFAULT '{}'::jsonb,
  propuesta text,
  decision text,
  servicio_id uuid,
  deuda_id uuid,
  subido_por uuid,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_recibo PRIMARY KEY (id),
  CONSTRAINT fk_recibo_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_recibo_servicio_id_servicio FOREIGN KEY (servicio_id)
    REFERENCES servicio (id) ON DELETE SET NULL,
  CONSTRAINT fk_recibo_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE SET NULL,
  CONSTRAINT fk_recibo_subido_por_usuario FOREIGN KEY (subido_por) REFERENCES usuario (id),
  CONSTRAINT uq_recibo_gerente_id_hash_sha256_pagina UNIQUE (gerente_id, hash_sha256, pagina),
  CONSTRAINT ck_recibo_archivo_tipo CHECK (archivo_tipo IN ('jpg', 'png', 'pdf', 'heic')),
  CONSTRAINT ck_recibo_hash_sha256 CHECK (hash_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_recibo_pagina CHECK (pagina > 0),
  CONSTRAINT ck_recibo_origen CHECK (origen IN ('subida', 'correo', 'robot')),
  CONSTRAINT ck_recibo_estado CHECK (
    estado IN ('procesando', 'listo', 'error', 'pendiente_lectura')
  ),
  CONSTRAINT ck_recibo_propuesta CHECK (
    propuesta IN ('agregar_pagar', 'solo_agregar', 'crear_servicio', 'ignorar')
  ),
  CONSTRAINT ck_recibo_decision CHECK (decision IN ('aceptada', 'ignorada'))
);
CREATE INDEX ix_recibo_servicio_id ON recibo (servicio_id);
CREATE INDEX ix_recibo_deuda_id ON recibo (deuda_id);
CREATE INDEX ix_recibo_subido_por ON recibo (subido_por);
CREATE TRIGGER tg_recibo_actualizado_en BEFORE UPDATE ON recibo
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE carga_qr (
  id uuid DEFAULT uuid_generate_v7(),
  usuario_id uuid NOT NULL,
  tipo text NOT NULL,
  deuda_id uuid,
  token_hash text NOT NULL,
  expira_en timestamptz NOT NULL,
  usado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_carga_qr PRIMARY KEY (id),
  CONSTRAINT fk_carga_qr_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE CASCADE,
  CONSTRAINT fk_carga_qr_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE CASCADE,
  CONSTRAINT uq_carga_qr_token_hash UNIQUE (token_hash),
  CONSTRAINT ck_carga_qr_tipo CHECK (tipo IN ('comprobante', 'recibo'))
);
CREATE INDEX ix_carga_qr_usuario_id ON carga_qr (usuario_id);
CREATE INDEX ix_carga_qr_deuda_id ON carga_qr (deuda_id);

CREATE TABLE conciliacion (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  medio_pago_id uuid NOT NULL,
  archivo_url text NOT NULL,
  hash_sha256 text NOT NULL,
  periodo date NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_conciliacion PRIMARY KEY (id),
  CONSTRAINT fk_conciliacion_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_conciliacion_medio_pago_id_medio_pago FOREIGN KEY (medio_pago_id)
    REFERENCES medio_pago (id),
  CONSTRAINT uq_conciliacion_gerente_id_hash_sha256 UNIQUE (gerente_id, hash_sha256),
  CONSTRAINT ck_conciliacion_periodo CHECK (extract(day FROM periodo) = 1)
);
CREATE INDEX ix_conciliacion_medio_pago_id ON conciliacion (medio_pago_id);

CREATE TABLE movimiento_conciliacion (
  id uuid DEFAULT uuid_generate_v7(),
  conciliacion_id uuid NOT NULL,
  fecha date NOT NULL,
  descripcion text NOT NULL,
  monto numeric(12,2) NOT NULL,
  deuda_id uuid,
  estado text NOT NULL DEFAULT 'sin_deuda',
  manual boolean NOT NULL DEFAULT false,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_movimiento_conciliacion PRIMARY KEY (id),
  CONSTRAINT fk_movimiento_conciliacion_conciliacion_id_conciliacion FOREIGN KEY (conciliacion_id)
    REFERENCES conciliacion (id) ON DELETE CASCADE,
  CONSTRAINT fk_movimiento_conciliacion_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE SET NULL,
  CONSTRAINT ck_movimiento_conciliacion_estado CHECK (estado IN ('conciliado', 'sin_deuda')),
  CONSTRAINT ck_movimiento_conciliacion_monto CHECK (monto <> 0)
);
CREATE INDEX ix_movimiento_conciliacion_conciliacion_id ON movimiento_conciliacion (conciliacion_id);
CREATE INDEX ix_movimiento_conciliacion_deuda_id ON movimiento_conciliacion (deuda_id);
CREATE TRIGGER tg_movimiento_conciliacion_actualizado_en BEFORE UPDATE ON movimiento_conciliacion
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE reembolso (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  asistente_id uuid NOT NULL,
  comprobante_id uuid NOT NULL,
  monto numeric(12,2) NOT NULL,
  estado text NOT NULL DEFAULT 'pendiente',
  motivo text,
  medio_reembolso text,
  resuelto_por uuid,
  reembolsado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_reembolso PRIMARY KEY (id),
  CONSTRAINT fk_reembolso_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_reembolso_asistente_id_usuario FOREIGN KEY (asistente_id) REFERENCES usuario (id),
  CONSTRAINT fk_reembolso_comprobante_id_comprobante FOREIGN KEY (comprobante_id)
    REFERENCES comprobante (id),
  CONSTRAINT fk_reembolso_resuelto_por_usuario FOREIGN KEY (resuelto_por) REFERENCES usuario (id),
  CONSTRAINT uq_reembolso_comprobante_id UNIQUE (comprobante_id),
  CONSTRAINT ck_reembolso_monto CHECK (monto > 0),
  CONSTRAINT ck_reembolso_estado CHECK (
    estado IN ('pendiente', 'aprobado', 'rechazado', 'reembolsado')
  )
);
CREATE INDEX ix_reembolso_gerente_id ON reembolso (gerente_id);
CREATE INDEX ix_reembolso_asistente_id ON reembolso (asistente_id);
CREATE INDEX ix_reembolso_resuelto_por ON reembolso (resuelto_por);
CREATE TRIGGER tg_reembolso_actualizado_en BEFORE UPDATE ON reembolso
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

-- Seguimiento y robots

CREATE TABLE notificacion (
  id uuid DEFAULT uuid_generate_v7(),
  usuario_id uuid NOT NULL,
  tipo text NOT NULL,
  titulo text NOT NULL,
  mensaje text NOT NULL,
  deuda_id uuid,
  urgente boolean NOT NULL DEFAULT false,
  leida_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_notificacion PRIMARY KEY (id),
  CONSTRAINT fk_notificacion_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE CASCADE,
  CONSTRAINT fk_notificacion_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE CASCADE,
  CONSTRAINT ck_notificacion_tipo CHECK (
    tipo IN (
      'deuda_creada', 'deuda_pagada', 'por_vencer', 'vencida', 'comprobante_rechazado',
      'comprobante_en_revision', 'aprobacion_pendiente', 'orden_urgente', 'no_pude_pagar',
      'recordatorio_comprobante', 'comentario', 'robot_falla', 'reembolso'
    )
  )
);
CREATE INDEX ix_notificacion_usuario_id_creado_en ON notificacion (usuario_id, creado_en);
CREATE INDEX ix_notificacion_deuda_id ON notificacion (deuda_id);

CREATE TABLE preferencia_notificacion (
  usuario_id uuid NOT NULL,
  tipo text NOT NULL,
  canal text NOT NULL,
  activa boolean NOT NULL DEFAULT true,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_preferencia_notificacion PRIMARY KEY (usuario_id, tipo, canal),
  CONSTRAINT fk_preferencia_notificacion_usuario_id_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuario (id) ON DELETE CASCADE,
  CONSTRAINT ck_preferencia_notificacion_tipo CHECK (
    tipo IN (
      'deuda_creada', 'deuda_pagada', 'por_vencer', 'vencida', 'comprobante_rechazado',
      'comprobante_en_revision', 'aprobacion_pendiente', 'orden_urgente', 'no_pude_pagar',
      'recordatorio_comprobante', 'comentario', 'robot_falla', 'reembolso'
    )
  ),
  CONSTRAINT ck_preferencia_notificacion_canal CHECK (canal IN ('app', 'correo', 'whatsapp'))
);
CREATE TRIGGER tg_preferencia_notificacion_actualizado_en BEFORE UPDATE ON preferencia_notificacion
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE exportacion (
  id uuid DEFAULT uuid_generate_v7(),
  gerente_id uuid NOT NULL,
  usuario_id uuid NOT NULL,
  tipo text NOT NULL,
  parametros jsonb NOT NULL DEFAULT '{}'::jsonb,
  estado text NOT NULL DEFAULT 'procesando',
  archivo_url text,
  expira_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_exportacion PRIMARY KEY (id),
  CONSTRAINT fk_exportacion_gerente_id_usuario FOREIGN KEY (gerente_id) REFERENCES usuario (id),
  CONSTRAINT fk_exportacion_usuario_id_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id),
  CONSTRAINT ck_exportacion_tipo CHECK (
    tipo IN ('comprobantes_lote', 'reporte_mensual', 'auditoria')
  ),
  CONSTRAINT ck_exportacion_estado CHECK (estado IN ('procesando', 'lista', 'error'))
);
CREATE INDEX ix_exportacion_gerente_id ON exportacion (gerente_id);
CREATE INDEX ix_exportacion_usuario_id ON exportacion (usuario_id);
CREATE TRIGGER tg_exportacion_actualizado_en BEFORE UPDATE ON exportacion
  FOR EACH ROW EXECUTE FUNCTION fijar_actualizado_en();

CREATE TABLE ejecucion_robot (
  id uuid DEFAULT uuid_generate_v7(),
  empresa_id uuid NOT NULL,
  servicio_id uuid,
  deuda_id uuid,
  tarea text NOT NULL,
  estado text NOT NULL DEFAULT 'en_curso',
  detalle text,
  terminado_en timestamptz,
  creado_en timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_ejecucion_robot PRIMARY KEY (id),
  CONSTRAINT fk_ejecucion_robot_empresa_id_empresa FOREIGN KEY (empresa_id)
    REFERENCES empresa (id),
  CONSTRAINT fk_ejecucion_robot_servicio_id_servicio FOREIGN KEY (servicio_id)
    REFERENCES servicio (id) ON DELETE SET NULL,
  CONSTRAINT fk_ejecucion_robot_deuda_id_deuda FOREIGN KEY (deuda_id)
    REFERENCES deuda (id) ON DELETE SET NULL,
  CONSTRAINT ck_ejecucion_robot_tarea CHECK (tarea IN ('consultar', 'pagar', 'confirmar')),
  CONSTRAINT ck_ejecucion_robot_estado CHECK (
    estado IN ('en_curso', 'exito', 'fallo', 'captcha', 'bloqueado')
  )
);
CREATE INDEX ix_ejecucion_robot_empresa_id_creado_en ON ejecucion_robot (empresa_id, creado_en);
CREATE INDEX ix_ejecucion_robot_servicio_id ON ejecucion_robot (servicio_id);
CREATE INDEX ix_ejecucion_robot_deuda_id ON ejecucion_robot (deuda_id);
