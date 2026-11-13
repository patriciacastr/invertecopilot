"""Lectura de PDF por página con respaldo a OCR y caché.

Herramienta del curso: Document AI con PaddleOCR (sesión 10).

- Si la página tiene texto nativo útil, se usa tal cual (rápido y exacto).
- Si no (escaneo) o el texto es basura, se renderiza la página y se pasa por OCR.
- El resultado se guarda en data/cache/<hash>.<backend>.json: el OCR de un PDF de 50
  páginas se hace UNA vez, no durante el demo.

Backends: "paddle" (curso), "tesseract" (respaldo; requiere el binario instalado),
"auto" (paddle si está instalado, si no tesseract).
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Dict, List

import fitz  # PyMuPDF

MIN_CHARS = 40          # menos que esto => página sin texto útil
MIN_ALNUM_RATIO = 0.6   # texto "sucio" (capa de texto corrupta) => se re-lee con OCR
CACHE_DIR = os.environ.get("CACHE_DIR", "data/cache")

_paddle = None


def _alnum_ratio(text: str) -> float:
    t = re.sub(r"\s", "", text)
    return (sum(c.isalnum() for c in t) / len(t)) if t else 0.0


def _needs_ocr(text: str) -> bool:
    return len(text.strip()) < MIN_CHARS or _alnum_ratio(text) < MIN_ALNUM_RATIO


def _ocr_paddle(png_bytes: bytes) -> str:
    """PaddleOCR. Ajusta a la versión que usaste en la sesión 10 / tu tarea HW_04."""
    global _paddle
    import numpy as np
    from PIL import Image
    import io

    if _paddle is None:
        from paddleocr import PaddleOCR
        try:
            _paddle = PaddleOCR(lang="es", use_angle_cls=True, show_log=False)   # 2.x
        except Exception:
            _paddle = PaddleOCR(lang="es")                                        # 3.x
    img = np.array(Image.open(io.BytesIO(png_bytes)).convert("RGB"))
    if hasattr(_paddle, "predict"):                                               # 3.x
        res = _paddle.predict(img)
        lines = []
        for r in res:
            lines += list(r.get("rec_texts", []) if hasattr(r, "get") else r["rec_texts"])
        return "\n".join(lines)
    res = _paddle.ocr(img, cls=True)                                              # 2.x
    return "\n".join(l[1][0] for block in (res or []) if block for l in block)


def _ocr_tesseract(png_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        f.write(png_bytes)
        f.flush()
        out = subprocess.run(["tesseract", f.name, "-", "-l", "spa", "--psm", "4"],
                             capture_output=True, text=True)
    return out.stdout


def pick_backend(backend: str = "auto") -> str:
    if backend != "auto":
        return backend
    try:
        import paddleocr  # noqa: F401
        return "paddle"
    except ImportError:
        if shutil.which("tesseract"):
            return "tesseract"
        raise RuntimeError("No hay OCR disponible: instala paddleocr o tesseract.")


def _file_hash(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def extract_pages(pdf_path: str, backend: str = "auto", dpi: int = 200,
                  use_cache: bool = True, max_pages: int = None) -> List[Dict]:
    """Devuelve [{'page': 1, 'text': '...', 'ocr': bool}, ...] (páginas desde 1)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    h = _file_hash(pdf_path)
    # La caché se busca por contenido del PDF (da igual cómo lo renombres) y con cualquier
    # backend: así funciona aunque esta máquina no tenga OCR instalado.
    if use_cache and max_pages is None:
        hits = sorted(glob.glob(os.path.join(CACHE_DIR, f"{h}.*.json")))
        if hits:
            with open(hits[0], encoding="utf-8") as f:
                return json.load(f)
    be = pick_backend(backend)
    cache = os.path.join(CACHE_DIR, f"{h}.{be}.json")

    ocr_fn = _ocr_paddle if be == "paddle" else _ocr_tesseract
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc, start=1):
        if max_pages and i > max_pages:
            break
        text = page.get_text().strip()
        used_ocr = False
        if _needs_ocr(text):
            t0 = time.time()
            text = ocr_fn(page.get_pixmap(dpi=dpi).tobytes("png")).strip()
            used_ocr = True
            print(f"  OCR página {i}/{len(doc)}  ({time.time() - t0:.0f} s)", flush=True)
        pages.append({"page": i, "text": text, "ocr": used_ocr})

    if use_cache and max_pages is None:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(pages, f, ensure_ascii=False)
    return pages


def extract_pages_from_bytes(pdf_bytes: bytes, **kw) -> List[Dict]:
    """Para archivos subidos en Streamlit."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        path = f.name
    try:
        return extract_pages(path, **kw)
    finally:
        os.unlink(path)
