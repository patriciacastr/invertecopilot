"""Extracción estructurada con citas de página. Herramienta del curso: LLMs con salidas estructuradas (sesión 08).

Cada campo devuelve: valor + página + fragmento textual que lo sustenta.
Si el dato no está en el documento, el valor debe ser null (no inventar).
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Dato(BaseModel):
    valor: Optional[str] = Field(None, description="Valor extraído; null si no aparece en el documento")
    pagina: Optional[int] = Field(None, description="Página donde se encontró")
    fragmento: Optional[str] = Field(None, description="Texto literal corto que sustenta el valor")


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
    componentes: List[Dato]
    informacion_faltante: List[str] = Field(default_factory=list)


def extract_matrix(pages: list) -> dict:
    """TODO: llamar al LLM (misma API que usaste en la sesión 08) con salida estructurada
    MatrizProyecto, pasando el texto etiquetado por página: '[Página N] ...'.
    Luego VERIFICAR que cada 'fragmento' aparezca realmente en la página citada
    (si no aparece, marcar el dato como no verificado)."""
    raise NotImplementedError
