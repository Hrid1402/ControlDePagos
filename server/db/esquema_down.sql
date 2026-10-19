DROP TABLE IF EXISTS
  canal_pago, empresa_zona, empresa, inmueble, ubigeo,
  configuracion_ia, limite, medio_pago,
  auditoria, activacion_cuenta, token_restablecimiento, cambio_usuario, historial_contrasena, usuario
CASCADE;
DROP FUNCTION IF EXISTS fijar_actualizado_en();
DROP FUNCTION IF EXISTS uuid_generate_v7();
