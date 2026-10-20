"""Tareas en segundo plano con Celery y Beat sobre Redis.

La app está en celery_app.py, los horarios de Beat en horarios.py y la base común de las tareas
(reintentos, sesión propia y bloqueo) en base.py. El patrón de un job está en server/README.md.
"""
