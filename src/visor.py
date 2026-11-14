"""Muestra una página del PDF como imagen, con la cita resaltada cuando el PDF tiene texto digital."""
import re
from typing import Optional, Tuple

import fitz


def _consultas(fragmento: str):
    """Frases cada vez más cortas del fragmento, para que search_for encuentre alguna."""
    palabras = re.sub(r"\s+", " ", fragmento or "").strip().split(" ")
    for n in (10, 7, 5, 3):
        if len(palabras) >= n:
            yield " ".join(palabras[:n])
    if palabras and palabras[0]:
        yield " ".join(palabras)


def render_pagina(pdf_bytes: bytes, pagina: int, fragmento: Optional[str] = None,
                  dpi: int = 110) -> Tuple[bytes, bool]:
    """Devuelve (png, resaltado). En PDF escaneados no hay texto que resaltar: solo se muestra la página."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[max(0, min(pagina - 1, len(doc) - 1))]
    resaltado = False
    if fragmento and page.get_text().strip():
        for q in _consultas(fragmento):
            rects = page.search_for(q)
            if rects:
                for r in rects:
                    page.add_highlight_annot(r)
                resaltado = True
                break
    return page.get_pixmap(dpi=dpi).tobytes("png"), resaltado
