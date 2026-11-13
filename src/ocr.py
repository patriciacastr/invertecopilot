"""Lectura de PDF por página. Herramienta del curso: Document AI con PaddleOCR (sesión 10).

Estrategia: intentar texto nativo con PyMuPDF; si una página casi no tiene texto
(PDF escaneado), renderizar a imagen y pasar por PaddleOCR.
"""
from typing import List, Dict

import fitz  # PyMuPDF

MIN_CHARS = 40  # debajo de esto, la página se considera escaneada


def _ocr_page_image(png_bytes: bytes) -> str:
    # TODO: usar el mismo patrón de PaddleOCR de la sesión 10 / tu tarea HW_04.
    # Carga el modelo UNA sola vez (variable global o st.cache_resource).
    raise NotImplementedError


def extract_pages(pdf_bytes: bytes) -> List[Dict]:
    """Devuelve [{'page': 1, 'text': '...', 'ocr': False}, ...] (páginas desde 1)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        used_ocr = False
        if len(text) < MIN_CHARS:
            pix = page.get_pixmap(dpi=200)
            text = _ocr_page_image(pix.tobytes("png"))
            used_ocr = True
        pages.append({"page": i, "text": text, "ocr": used_ocr})
    return pages
