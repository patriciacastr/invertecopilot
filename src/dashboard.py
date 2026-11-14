"""Cifras del dashboard. Todo es código determinista: el LLM lee, el código calcula."""
import re
from typing import Dict, List, Optional, Tuple

from src.contraste import _numeros


def beneficiarios(matriz) -> Optional[int]:
    """Primer número entero (≥10) del texto de población beneficiaria, ej. '793 estudiantes...'."""
    txt = matriz.poblacion_beneficiaria.valor or ""
    for m in re.finditer(r"\d[\d,\.]*", txt):
        n = m.group(0).replace(",", "")
        if re.fullmatch(r"\d+", n) and int(n) >= 10:
            return int(n)
    return None


def inversion(matriz, registro: Optional[Dict] = None) -> Tuple[Optional[float], str]:
    """Monto de inversión y de dónde sale. El registro oficial manda si está disponible."""
    if registro:
        txt = (registro.get("costo_total_viable") or {}).get("valor")
        nums = _numeros(txt)
        if nums:
            return nums[-1], "Registro del Banco de Inversiones"
    nums = _numeros(matriz.monto_inversion.valor)
    return (nums[0], "Documento técnico") if nums else (None, "")


def brecha_pct(matriz) -> Optional[float]:
    cand = [matriz.brecha.valor or ""] + [f"{i.nombre} {i.valor}" for i in matriz.indicadores
                                          if "brecha" in (i.nombre or "").lower()]
    for t in cand:
        m = re.search(r"(\d+(?:[\.,]\d+)?)\s*%", t)
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def costos_tabla(matriz) -> List[Dict]:
    filas = [{"Partida": c.concepto, "Monto (S/)": c.monto, "Página": c.pagina,
              "Verificado": "✅" if c.verificado else "⚠️"} for c in matriz.costos if c.monto]
    return sorted(filas, key=lambda f: -f["Monto (S/)"])


def kpis(matriz, registro: Optional[Dict] = None) -> Dict:
    inv, fuente = inversion(matriz, registro)
    ben = beneficiarios(matriz)
    return {
        "inversion": inv, "fuente_inversion": fuente, "beneficiarios": ben,
        "costo_por_beneficiario": (inv / ben) if inv and ben else None,
        "brecha_pct": brecha_pct(matriz),
        "n_citas": sum(1 for r in _todas_las_citas(matriz) if r),
        "n_verificadas": sum(1 for r in _todas_las_citas(matriz) if r is True),
    }


def _todas_las_citas(matriz):
    from src.extract import Dato
    out = [getattr(matriz, k).verificado for k in type(matriz).model_fields
           if isinstance(getattr(matriz, k), Dato) and getattr(matriz, k).valor]
    out += [c.verificado for c in matriz.componentes]
    out += [c.verificado for c in matriz.costos] + [i.verificado for i in matriz.indicadores]
    return out
