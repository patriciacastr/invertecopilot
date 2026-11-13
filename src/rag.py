"""Chat con dos fuentes: documento cargado + corpus normativo. Herramienta del curso: RAG (sesión 08).

Regla: cada parte de la respuesta indica su origen:
  [Doc p.12]            -> del documento cargado
  [Norma: Directiva X, art. Y]  -> del corpus normativo
Si no hay evidencia en ninguna fuente, decirlo.
"""
from typing import List, Dict, Optional

CORPUS_DIR = "data/corpus"


def build_index():
    """TODO: leer PDFs de data/corpus, partir por artículo/sección, guardar metadatos
    (norma, versión, artículo, URL). Reutiliza la lógica de tu RAG normativo de contrataciones
    (y asegúrate de poder explicarla)."""
    raise NotImplementedError


def retrieve_norma(query: str, k: int = 4) -> List[Dict]:
    raise NotImplementedError


def answer(question: str, pages: Optional[List[Dict]]) -> str:
    """TODO: decidir fuente(s): si hay `pages`, buscar en el documento; si la pregunta es de
    teoría/norma, buscar en el corpus; si es mezcla, usar ambas. Responder con citas."""
    raise NotImplementedError
