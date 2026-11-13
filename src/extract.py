"""Extracción estructurada con citas de página y verificación.

Herramienta del curso: LLMs con salidas estructuradas (sesión 08).
Regla de oro: cada dato trae página + fragmento literal; después VERIFICAMOS por código
que el fragmento exista en esa página. Si no existe, el dato se marca como no verificado.
"""
import re
import unicodedata
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

KEYWORDS = ("problema", "brecha", "beneficiari", "objetivo", "component", "costo",
            "presupuesto", "alternativa", "población", "poblacion", "meta", "monto",
            "horizonte", "indicador", "inversión", "inversion")

SYSTEM = (
    "Eres un analista de inversión pública (Invierte.pe). Extrae SOLO lo que el documento dice. "
    "Si un dato no aparece, devuélvelo como null y agrégalo a 'informacion_faltante'. "
    "Para cada dato da la página (el número que aparece en [Página N]) y un fragmento "
    "LITERAL corto (máx. 25 palabras) copiado del texto. No inventes ni calcules."
)


class Dato(BaseModel):
    valor: Optional[str] = Field(None, description="Valor extraído; null si no aparece")
    pagina: Optional[int] = Field(None, description="Página donde se encontró")
    fragmento: Optional[str] = Field(None, description="Texto LITERAL corto que lo sustenta")
    verificado: Optional[bool] = Field(None, description="Lo completa el código, no el modelo")


class MatrizProyecto(BaseModel):
    nombre_proyecto: Dato
    cui: Dato
    entidad: Dato
    ubicacion: Dato
    problema_central: Dato
    brecha: Dato
    objetivo: Dato
    poblacion_beneficiaria: Dato
    monto_inversion: Dato
    componentes: List[Dato] = Field(default_factory=list)
    informacion_faltante: List[str] = Field(default_factory=list)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def fragment_in_page(fragmento: str, page_text: str) -> bool:
    """¿El fragmento aparece en la página? Tolera saltos de línea, tildes y ruido de OCR leve."""
    f, t = _norm(fragmento), _norm(page_text)
    if not f:
        return False
    if f in t:
        return True
    words = f.split()                      # respaldo: 85% de las palabras en el mismo orden aprox.
    hits = sum(1 for w in words if w in t)
    return len(words) >= 4 and hits / len(words) >= 0.85


def select_pages(pages: List[dict], budget_chars: int = 100000) -> List[dict]:
    """Si el documento es largo, prioriza las páginas con palabras clave (manteniendo el orden)."""
    total = sum(len(p["text"]) for p in pages)
    if total <= budget_chars:
        return pages
    scored = sorted(pages, key=lambda p: -sum(p["text"].lower().count(k) for k in KEYWORDS))
    chosen, used = [], 0
    for p in scored:
        if used + len(p["text"]) > budget_chars:
            continue
        chosen.append(p)
        used += len(p["text"])
    return sorted(chosen, key=lambda p: p["page"])


def build_prompt(pages: List[dict]) -> str:
    return "\n\n".join(f"[Página {p['page']}]\n{p['text']}" for p in pages)


def verify(matriz: MatrizProyecto, pages: List[dict]) -> MatrizProyecto:
    by_page = {p["page"]: p["text"] for p in pages}
    campos = [getattr(matriz, k) for k in MatrizProyecto.model_fields
              if isinstance(getattr(matriz, k), Dato)] + list(matriz.componentes)
    for d in campos:
        if d.valor is None:
            d.verificado = None
        elif d.pagina in by_page and d.fragmento:
            d.verificado = fragment_in_page(d.fragmento, by_page[d.pagina])
        else:
            d.verificado = False
    return matriz


def extract_matrix(pages: List[dict], llm: Optional[Callable] = None) -> MatrizProyecto:
    if llm is None:
        from src.llm import structured as llm
    sel = select_pages(pages)
    matriz = llm(SYSTEM, build_prompt(sel), MatrizProyecto)
    return verify(matriz, pages)


def matrix_rows(m: MatrizProyecto) -> List[dict]:
    """Filas para mostrar en Streamlit (st.dataframe)."""
    rows = []
    for k in MatrizProyecto.model_fields:
        v = getattr(m, k)
        if isinstance(v, Dato):
            rows.append({"campo": k, "valor": v.valor, "página": v.pagina,
                         "fragmento": v.fragmento, "verificado": v.verificado})
    for i, c in enumerate(m.componentes, 1):
        rows.append({"campo": f"componente_{i}", "valor": c.valor, "página": c.pagina,
                     "fragmento": c.fragmento, "verificado": c.verificado})
    return rows
