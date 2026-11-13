"""Parser determinista de las exportaciones del Banco de Inversiones (Formato 07-A / Formato 01).

Estas exportaciones traen texto nativo (no son escaneos), con etiquetas fijas. Por eso la
capa 1 de extracción es por reglas: es rápida, gratis y siempre cita la página.
El LLM (src/extract.py) se reserva para lo que las reglas no resuelven (texto libre,
inconsistencias, preguntas).
"""
import re
from typing import Dict, List, Optional

import fitz  # PyMuPDF

SPLIT = re.compile(r"\s{2,}")


def read_pages(pdf_path: str) -> List[Dict]:
    """Texto por página con el layout preservado (columnas separadas por espacios)."""
    doc = fitz.open(pdf_path)
    pages = []
    for i, p in enumerate(doc, start=1):
        # 'blocks' ordenados por posición mantienen mejor las filas de las tablas del BI
        words = p.get_text("words")
        rows: Dict[int, list] = {}
        for x0, y0, x1, y1, w, *_ in words:
            rows.setdefault(round(y0 / 3), []).append((x0, w))
        lines = []
        for key in sorted(rows):
            cells, last_x = [], None
            line = ""
            for x, w in sorted(rows[key]):
                gap = "  " if (last_x is not None and x - last_x > 18) else " "
                line += (gap if line else "") + w
                last_x = x + len(w) * 4.2
            lines.append(line)
        pages.append({"page": i, "text": "\n".join(lines)})
    return pages


def _find(pages, pattern, flags=re.I):
    for pg in pages:
        m = re.search(pattern, pg["text"], flags)
        if m:
            return pg["page"], m
    return None, None


def _dato(valor: Optional[str], pagina: Optional[int]) -> Dict:
    valor = re.sub(r"\s+", " ", valor).strip() if valor else None
    return {"valor": valor or None, "pagina": pagina if valor else None}


def _after_label(pages, label, stop=None, max_lines=8):
    """Valor a la derecha de una etiqueta + líneas de continuación hasta una línea que sea otra etiqueta."""
    for pg in pages:
        lines = pg["text"].split("\n")
        for i, ln in enumerate(lines):
            if re.search(label, ln, re.I):
                parts = [p for p in SPLIT.split(ln.strip()) if p]
                # el valor es lo que viene después de la etiqueta
                m = re.search(label, ln, re.I)
                resto = ln[m.end():].strip(" :")
                buf = [resto] if resto else []
                for nxt in lines[i + 1: i + 1 + max_lines]:
                    if stop and re.search(stop, nxt, re.I):
                        break
                    if re.match(r"^\s*(\d+(\.\d+)*\.?\s|[A-D]\.\s|¿)", nxt):
                        break
                    buf.append(nxt.strip())
                return _dato(" ".join(buf), pg["page"])
    return _dato(None, None)


def parse_bi(pdf_path: str) -> Dict:
    pages = read_pages(pdf_path)
    out: Dict = {"archivo": pdf_path.split("/")[-1], "n_paginas": len(pages)}

    p, m = _find(pages, r"(FORMATO[^\n]*)")
    out["formato"] = _dato(m.group(1).strip() if m else None, p)
    p, m = _find(pages, r"Fecha de registro:\s*([\d/]+)")
    out["fecha_registro"] = _dato(m.group(1) if m else None, p)
    p, m = _find(pages, r"Fecha de viabilidad:\s*([\d/]+)")
    out["fecha_viabilidad"] = _dato(m.group(1) if m else None, p)
    p, m = _find(pages, r"C[oó]digo [uú]nico de inversiones\s+(\d{6,8})")
    out["cui"] = _dato(m.group(1) if m else None, p)
    p, m = _find(pages, r"Situaci[oó]n:\s*([^\n]+)")
    out["situacion"] = _dato(m.group(1) if m else None, p)

    # Nombre: 07-A lo trae en la(s) línea(s) siguiente(s) a la etiqueta; Formato 01 en "NOMBRE DEL PROYECTO DE INVERSIÓN"
    nombre = _after_label(pages, r"NOMBRE DEL PROYECTO DE INVERSI[OÓ]N", stop=r"Objeto de intervenci|Indique convenio")
    if not nombre["valor"]:
        for pg in pages:
            ls = pg["text"].split("\n")
            for i, ln in enumerate(ls):
                if re.search(r"Nombre del proyecto de inversi[oó]n \(generada", ln, re.I):
                    cand = [ls[i + 1].strip()] if not ls[i].strip().endswith("1.4)") or i + 1 >= len(ls) else [ls[i + 1].strip()]
                    if i + 2 < len(ls) and not re.search(r"C[oó]digo", ls[i + 2]):
                        cand.append(ls[i + 2].strip())
                    nombre = _dato(" ".join(cand), pg["page"])
                    break
            if nombre["valor"]:
                break
    if nombre["valor"]:
        nombre["valor"] = re.sub(r"^\(generada[^)]*\)\s*", "", nombre["valor"])
        nombre["valor"] = re.sub(r"\s*C[oó]digo [uú]nico de inversiones.*$", "", nombre["valor"], flags=re.I).strip()
    out["nombre_proyecto"] = nombre

    for campo, etiqueta in [
        ("funcion", r"^\s*Funci[oó]n\s+(?=\d)"), ("sector", r"Sector responsable\s+"),
        ("tipologia", r"Tipolog[ií]a de proyecto\s+"),
    ]:
        out[campo] = _after_label(pages, etiqueta, max_lines=0)
    # Entidad: la primera es la de la OPMI
    out["entidad"] = _after_label(pages, r"^\s*Entidad\s+", max_lines=0)
    out["objetivo_central"] = _after_label(pages, r"Descripci[oó]n del objetivo central del proyecto", stop=r"Nombre del indicador", max_lines=4)
    out["indicador_objetivo"] = _after_label(pages, r"Nombre del indicador para la medici[oó]n del objetivo central", max_lines=0)
    out["beneficiarios"] = _after_label(pages, r"Denominaci[oó]n de los beneficiarios directos", stop=r"Unidad de medida", max_lines=3)
    p, m = _find(pages, r"Costo total de inversi[oó]n viable\s+([\d,\.]+)")
    out["costo_total_viable"] = _dato(m.group(1) if m else None, p)
    out["alternativa_recomendada"] = _after_label(pages, r"Alternativa 1 \(Recomendada\)", stop=r"^\s*4\.", max_lines=14)
    return out


if __name__ == "__main__":
    import json, sys
    for f in sys.argv[1:]:
        print(json.dumps(parse_bi(f), ensure_ascii=False, indent=2))
