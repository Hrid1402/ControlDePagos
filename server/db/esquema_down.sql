DROP TABLE IF EXISTS
  ejecucion_robot, exportacion, preferencia_notificacion, notificacion,
  reembolso, movimiento_conciliacion, conciliacion, carga_qr, recibo, comprobante_deuda,
  comprobante,
  solicitud_aprobacion, pago, reporte_problema, orden_pago,
  regla_alerta, comentario, historial_monto, deuda, prestamo, recurrencia, servicio, categoria,
  canal_pago, empresa_zona, empresa, inmueble, ubigeo,
  configuracion_ia, limite, medio_pago,
  auditoria, activacion_cuenta, token_restablecimiento, cambio_usuario, historial_contrasena, usuario
CASCADE;
DROP FUNCTION IF EXISTS fijar_actualizado_en();
DROP FUNCTION IF EXISTS uuid_generate_v7();
