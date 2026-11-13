"""Contraste entre lo que dice el documento técnico y lo que está registrado en el Banco de Inversiones.

Es el valor diferencial del producto: no solo extrae, también detecta diferencias entre fuentes.
Todo es código determinista (sin LLM), así que cada resultado se puede explicar.
"""
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional

SIMILITUD_MIN = 0.90        # nombres/entidades: coinciden si superan este ratio
SIMILITUD_REVISAR = 0.70    # entre 0.70 y 0.90: redacción distinta, conviene revisar a mano
TOLERANCIA_SOLES = 1.0      # montos: se consideran iguales si difieren menos de S/ 1


def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower().replace("ó", "o").replace("í", "i")
                  .replace("á", "a").replace("é", "e").replace("ú", "u")).strip()


def _similares(a: Optional[str], b: Optional[str]) -> float:
    """Parecido entre dos textos (0-1). Si el texto corto está casi completo dentro del largo
    (el documento suele escribir el nombre más extenso que el registro), cuenta como coincidencia."""
    na, nb = " ".join(_norm(a).split()), " ".join(_norm(b).split())
    ratio = SequenceMatcher(None, na, nb).ratio()
    corto, largo = sorted([set(na.split()), set(nb.split())], key=len)
    if corto and len(corto & largo) / len(corto) >= 0.95:
        return max(ratio, 1.0)
    return ratio


def _numeros(texto: Optional[str]) -> List[float]:
    out = []
    for m in re.finditer(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+", texto or ""):
        try:
            out.append(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out


def _a_float(texto: Optional[str]) -> Optional[float]:
    n = _numeros(texto)
    return n[-1] if n else None


def contrastar(matriz, registro: Dict) -> List[Dict]:
    """matriz: MatrizProyecto (documento). registro: salida de parse_bi (Banco de Inversiones)."""
    filas = []

    # CUI
    cui_doc, cui_reg = matriz.cui.valor, registro["cui"]["valor"]
    if not cui_doc and cui_reg:
        res = "ℹ️ el documento no lo trae; se toma del registro"
    else:
        res = "✅ coincide" if (cui_doc or "").strip() == (cui_reg or "").strip() else "⚠️ difiere"
    filas.append({"campo": "CUI", "documento": cui_doc, "registro": cui_reg, "resultado": res})

    # Nombre y entidad (texto parecido)
    for campo, doc, reg in [
        ("Nombre del proyecto", matriz.nombre_proyecto.valor, registro["nombre_proyecto"]["valor"]),
        ("Entidad", matriz.entidad.valor, registro["entidad"]["valor"]),
    ]:
        if not doc or not reg:
            res = "ℹ️ falta en una de las fuentes"
        else:
            r = _similares(doc, reg)
            if r >= SIMILITUD_MIN:
                res = "✅ coincide"
            elif r >= SIMILITUD_REVISAR:
                res = f"🔎 parecido ({r:.0%}): redacción distinta, revisar"
            else:
                res = f"⚠️ difiere (parecido {r:.0%})"
        filas.append({"campo": campo, "documento": doc, "registro": reg, "resultado": res})

    # Monto: el documento puede traer varios importes (con y sin control concurrente)
    reg_monto = _a_float(registro.get("costo_total_viable", {}).get("valor"))
    doc_importes = _numeros(" ".join(filter(None, [matriz.monto_inversion.valor, matriz.monto_inversion.fragmento])))
    if reg_monto is None or not doc_importes:
        res = "ℹ️ falta en una de las fuentes"
    else:
        cercano = min(doc_importes, key=lambda x: abs(x - reg_monto))
        dif = cercano - reg_monto
        if abs(dif) <= TOLERANCIA_SOLES:
            res = "✅ coincide" + (f" (dif. S/ {dif:+.2f})" if abs(dif) > 0 else "")
        else:
            res = f"⚠️ difiere en S/ {dif:+,.2f}"
    filas.append({
        "campo": "Costo de inversión (S/)",
        "documento": " / ".join(f"{x:,.2f}" for x in doc_importes) or None,
        "registro": f"{reg_monto:,.2f}" if reg_monto is not None else None,
        "resultado": res,
    })
    return filas


def completar_con_registro(rows, registro):
    """Rellena en las filas de la matriz los campos vacíos que el registro sí trae (hoy: CUI).
    La fuente queda visible en la columna 'fragmento' y 'verificado' marca 'registro'."""
    if not registro:
        return rows
    out = []
    for r in rows:
        r = dict(r)
        if r["campo"] == "cui" and not r["valor"] and (registro.get("cui") or {}).get("valor"):
            r["valor"] = registro["cui"]["valor"]
            r["página"] = registro["cui"].get("pagina")
            r["fragmento"] = "Registro del Banco de Inversiones"
            r["verificado"] = "registro"
        out.append(r)
    return out
