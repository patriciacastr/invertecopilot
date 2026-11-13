"""Procesa todos los PDFs de data/pdfs y deja el texto por página en data/cache.

Uso:  python -m src.ingest data/pdfs [--backend tesseract|paddle|auto]
Corre esto ANTES del demo: así el OCR no se hace en vivo.
"""
import argparse
import glob
import os
import time

from src.ocr import extract_pages, pick_backend

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("carpeta", nargs="?", default="data/pdfs")
    ap.add_argument("--backend", default="auto")
    a = ap.parse_args()
    be = pick_backend(a.backend)
    print(f"OCR backend: {be}\n{'archivo':45} págs  OCR  caracteres  seg")
    for f in sorted(glob.glob(os.path.join(a.carpeta, "*.pdf"))):
        t = time.time()
        pages = extract_pages(f, backend=be)
        n_ocr = sum(p["ocr"] for p in pages)
        chars = sum(len(p["text"]) for p in pages)
        print(f"{os.path.basename(f)[:44]:45} {len(pages):4}  {n_ocr:3}  {chars:9}  {time.time()-t:5.1f}")
