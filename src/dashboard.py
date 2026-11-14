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


def _es_subtotal(monto: float, otros: List[float], tol: float = 1.0) -> bool:
    """¿Existe un subconjunto (≥2) de `otros` que sume `monto` (±tol soles)? Entonces `monto` es un subtotal."""
    otros = [o for o in otros if o > 0][:16]
    sumas = {0.0: 0}
    for o in otros:
        for t, n in list(sumas.items()):
            sumas.setdefault(round(t + o, 2), n + 1)
    return any(n >= 2 and abs(t - monto) <= tol for t, n in sumas.items())


def costos_tabla(matriz) -> List[Dict]:
    """Partidas de costo ordenadas de mayor a menor. 'Tipo' marca los subtotales (montos que son la
    suma de otras partidas leídas) para no contarlos dos veces."""
    filas = [{"Partida": c.concepto, "Monto (S/)": c.monto, "Página": c.pagina,
              "Verificado": "✅" if c.verificado else "⚠️"} for c in matriz.costos if c.monto]
    filas.sort(key=lambda f: -f["Monto (S/)"])
    marcados = {i for i, f in enumerate(filas)
                if re.match(r"\s*(sub\s*-?\s*total|total|costo\s+total)\b", str(f["Partida"]), re.I)}
    for i, f in enumerate(filas):
        if i in marcados:
            continue
        menores = [g["Monto (S/)"] for j, g in enumerate(filas) if j > i and j not in marcados]
        if _es_subtotal(f["Monto (S/)"], menores):
            marcados.add(i)
    for i, f in enumerate(filas):
        f["Tipo"] = "Subtotal" if i in marcados else "Partida"
    return filas


def partidas_base(filas: List[Dict]) -> List[Dict]:
    """Solo las partidas que no son subtotales."""
    return [f for f in filas if f.get("Tipo") != "Subtotal"]


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
