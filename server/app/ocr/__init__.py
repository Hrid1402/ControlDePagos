"""Lectura de comprobantes: OCR con PaddleOCR (motor.py).

PaddleOCR va en el grupo ocr de pyproject (uv sync --group ocr), que solo instala el worker de
la cola ocr: la API y el resto de workers no lo necesitan ni lo importan.
"""
