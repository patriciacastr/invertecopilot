"""Alertas de revisión: lo que conviene mirar a mano antes de usar la matriz. Todo es código, sin modelo."""
from typing import Dict, List, Optional, Tuple

from src.contraste import _numeros, contrastar
from src.dashboard import beneficiarios, costos_tabla, inversion, partidas_base
from src.extract import Dato

ETIQUETAS = {"nombre_proyecto": "nombre del proyecto", "entidad": "entidad", "ubicacion": "ubicación",
             "problema_central": "problema central", "brecha": "brecha", "objetivo": "objetivo",
             "poblacion_beneficiaria": "población beneficiaria", "monto_inversion": "monto de inversión",
             "cui": "CUI"}


def _montos_distintos(texto: str) -> List[float]:
    out: List[float] = []
    for n in sorted(_numeros(texto)):
        if n >= 1000 and all(abs(n - o) > 1 for o in out):
            out.append(n)
    return out


def alertas(matriz, registro: Optional[Dict] = None) -> List[Tuple[str, str]]:
    """Lista de (nivel, texto). Niveles: 'error' (revisar sí o sí), 'aviso', 'info'."""
    out: List[Tuple[str, str]] = []
    cui_registro = bool(registro and (registro.get("cui") or {}).get("valor"))

    # Citas que no se encontraron en la página indicada
    malas = [ETIQUETAS.get(k, k) for k in type(matriz).model_fields
             if isinstance(getattr(matriz, k), Dato) and getattr(matriz, k).valor
             and getattr(matriz, k).verificado is False]
    malas += [f"componente: {c.valor[:40]}" for c in matriz.componentes if c.valor and c.verificado is False]
    malas += [f"partida: {c.concepto}" for c in matriz.costos if c.verificado is False]
    malas += [f"indicador: {i.nombre}" for i in matriz.indicadores if i.verificado is False]
    if malas:
        out.append(("error", "Citas que no se encontraron en la página indicada (revisar a mano): " + "; ".join(malas) + "."))

    # Contraste con el registro
    if registro:
        for f in contrastar(matriz, registro):
            r = f["resultado"]
            if r.startswith("⚠️"):
                out.append(("error", f"{f['campo']}: el documento y el registro no coinciden ({r.replace('⚠️ ', '')})."))
            elif r.startswith("🔎"):
                out.append(("aviso", f"{f['campo']}: redacción distinta entre documento y registro; conviene revisar."))
    else:
        out.append(("info", "No se contrastó con el registro del Banco de Inversiones: elige o sube uno en la barra lateral."))

    # Varios montos en el documento
    montos = _montos_distintos(f"{matriz.monto_inversion.valor or ''} {matriz.monto_inversion.fragmento or ''}")
    if len(montos) > 1:
        out.append(("aviso", "El documento menciona más de un monto de inversión: "
                    + "; ".join(f"S/ {m:,.2f}" for m in montos)
                    + ". Confirma cuál corresponde (por ejemplo, con o sin control concurrente)."))

    # Campos que no aparecen
    faltan = [ETIQUETAS[k] for k in ETIQUETAS if isinstance(getattr(matriz, k), Dato)
              and not getattr(matriz, k).valor and not (k == "cui" and cui_registro)]
    if faltan:
        out.append(("aviso", "No aparece en el documento: " + ", ".join(faltan) + "."))
    if beneficiarios(matriz) is None:
        out.append(("info", "No se encontró el número de beneficiarios, por eso no se calcula el costo por beneficiario."))

    # Cobertura de las partidas de costo
    inv, _ = inversion(matriz, registro)
    suma = sum(c["Monto (S/)"] for c in partidas_base(costos_tabla(matriz)))
    if inv and suma:
        if suma / inv < 0.6:
            out.append(("info", f"Las partidas leídas cubren el {suma / inv:.0%} de la inversión: el documento no las lista todas o no se leyeron todas."))
        elif suma / inv > 1.05:
            out.append(("aviso", f"Las partidas leídas suman el {suma / inv:.0%} de la inversión: puede haber subtotales repetidos."))
    elif not matriz.costos:
        out.append(("info", "No se encontraron partidas de costo en el documento."))
    return out
