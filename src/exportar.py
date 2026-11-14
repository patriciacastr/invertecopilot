"""Exporta la matriz a Excel (el destino final que mencionaron las dos personas entrevistadas)."""
import io
from typing import Dict, Optional

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.contraste import completar_con_registro, contrastar
from src.dashboard import costos_tabla, kpis
from src.extract import matrix_rows

_VERIF = {True: "Verificado", False: "No verificado", None: "", "registro": "Del registro BI"}


def _formato(ws, anchos: Dict[str, int], soles_col: Optional[str] = None) -> None:
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F6FED")
    for col, ancho in anchos.items():
        ws.column_dimensions[col].width = ancho
    for fila in ws.iter_rows(min_row=2):
        for c in fila:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    if soles_col:
        for c in ws[soles_col][1:]:
            c.number_format = "#,##0.00"
    ws.freeze_panes = "A2"


def matriz_a_excel(matriz, registro: Optional[Dict] = None, documento: str = "") -> bytes:
    k = kpis(matriz, registro)
    resumen = pd.DataFrame([
        ("Documento", documento), ("Proyecto", matriz.nombre_proyecto.valor),
        ("Inversión (S/)", k["inversion"]), ("Fuente de la inversión", k["fuente_inversion"]),
        ("Beneficiarios", k["beneficiarios"]), ("Costo por beneficiario (S/)", k["costo_por_beneficiario"]),
        ("Brecha (%)", k["brecha_pct"]), ("Citas verificadas", f"{k['n_verificadas']} de {k['n_citas']}"),
    ], columns=["Dato", "Valor"])
    filas = completar_con_registro(matrix_rows(matriz), registro)
    tabla = pd.DataFrame([{"Campo": r["campo"], "Valor": r["valor"], "Página": r["página"],
                           "Cita textual": r["fragmento"], "Estado": _VERIF.get(r["verificado"], "")}
                          for r in filas])
    costos = pd.DataFrame([{"Partida": c["Partida"], "Monto (S/)": c["Monto (S/)"], "Página": c["Página"],
                            "Estado": "Verificado" if c["Verificado"] == "✅" else "No verificado"}
                           for c in costos_tabla(matriz)], columns=["Partida", "Monto (S/)", "Página", "Estado"])
    ind = pd.DataFrame([{"Indicador": i.nombre, "Valor": i.valor, "Página": i.pagina,
                         "Cita textual": i.fragmento, "Estado": _VERIF.get(i.verificado, "")}
                        for i in matriz.indicadores], columns=["Indicador", "Valor", "Página", "Cita textual", "Estado"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        resumen.to_excel(xl, sheet_name="Resumen", index=False)
        tabla.to_excel(xl, sheet_name="Matriz", index=False)
        costos.to_excel(xl, sheet_name="Costos", index=False)
        ind.to_excel(xl, sheet_name="Indicadores", index=False)
        _formato(xl.sheets["Resumen"], {"A": 30, "B": 80})
        _formato(xl.sheets["Matriz"], {"A": 24, "B": 70, "C": 9, "D": 70, "E": 16})
        _formato(xl.sheets["Costos"], {"A": 50, "B": 18, "C": 9, "D": 16}, soles_col="B")
        _formato(xl.sheets["Indicadores"], {"A": 40, "B": 20, "C": 9, "D": 60, "E": 16})
        if registro:
            con = pd.DataFrame(contrastar(matriz, registro))
            con.columns = ["Campo", "Documento", "Registro BI", "Resultado"]
            con.to_excel(xl, sheet_name="Contraste", index=False)
            _formato(xl.sheets["Contraste"], {"A": 24, "B": 60, "C": 60, "D": 40})
    return buf.getvalue()
