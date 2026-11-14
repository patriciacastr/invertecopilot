"""InvierteCopilot - app principal (Streamlit).

Flujo: elegir o subir un PDF -> texto por página (caché/OCR) -> matriz con citas verificadas
-> chat (documento + normativa).
Para correr:  streamlit run app.py
"""
import glob
import html
import os
import re

import pandas as pd
import streamlit as st

import tempfile
import time

import altair as alt

from src.alertas import alertas
from src.visor import render_pagina
from src.contraste import completar_con_registro, contrastar
from src.dashboard import costos_tabla, kpis
from src import llm as _llm
from src.exportar import matriz_a_excel
from src.extract import extract_matrix, matrix_rows
from src.parse_bi import parse_bi
from src.ocr import extract_pages, extract_pages_from_bytes

st.set_page_config(page_title="InvierteCopilot", layout="wide")
st.title("InvierteCopilot")
st.caption("Asistente para revisar fichas técnicas de Invierte.pe, con citas de página y de norma.")



def _soles(x):
    return f"S/ {x:,.0f}" if x else "—"


_CSS = """
<style>
.kpi{border-radius:14px;padding:14px 18px;border:1px solid;min-height:118px;}
.kpi .et{font-size:.76rem;letter-spacing:.05em;text-transform:uppercase;opacity:.85;font-weight:600;}
.kpi .val{font-size:2rem;font-weight:800;line-height:1.15;margin-top:4px;}
.kpi .sub{font-size:.74rem;opacity:.75;margin-top:4px;}
.caja{border-radius:14px;padding:14px 18px;border:1px solid;margin-bottom:4px;}
.caja .tit{font-weight:800;font-size:1rem;margin-bottom:6px;}
.caja .txt{font-size:.95rem;line-height:1.5;}
.caja .pie{font-size:.78rem;opacity:.8;margin-top:8px;}
.az{background:#e8f1ff;border-color:#b9d3ff;color:#14304f;}
.vd{background:#e6f6ee;border-color:#b6e3cb;color:#0f3d2b;}
.tabla{width:100%;border-collapse:collapse;font-size:.9rem;margin-top:4px;}
.tabla th{text-align:left;background:#eef4ff;padding:8px 12px;font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;border-bottom:2px solid #cfe0ff;}
.tabla td{padding:9px 12px;border-bottom:1px solid #e6ecf5;vertical-align:top;line-height:1.4;}
.tabla td.num{white-space:nowrap;text-align:right;}
.tabla th:nth-child(n+2){text-align:right;}
.tabla tbody tr:hover{background:#f6faff;}
.barra{background:#cfe0ff;border-radius:8px;height:14px;margin:6px 0;}
.barra>div{background:#2f6fed;height:14px;border-radius:8px;}
[data-testid="stDownloadButton"] button{background:#1f8a5b;color:#fff;border:none;font-weight:700;
  font-size:1rem;padding:.65rem 1.2rem;border-radius:12px;}
[data-testid="stDownloadButton"] button:hover{background:#17724a;color:#fff;}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

_NUM = re.compile(r"(S/\.?\s?[\d,]+(?:\.\d+)?|\d[\d,\.]*\s?%|\d[\d,\.]*(?=\s(?:estudiantes|alumnos|personas|habitantes|beneficiari|aulas)))")


def _resaltar(txt: str) -> str:
    """Escapa el texto y pone en negrita las cifras que importan (montos, porcentajes, poblaciones)."""
    return _NUM.sub(r"<b>\1</b>", html.escape(txt))


@st.cache_data(show_spinner=False, max_entries=64)
def _pagina_img(pdf_bytes: bytes, pagina: int, fragmento: str):
    return render_pagina(pdf_bytes, pagina, fragmento)


def _ver_pagina(clave: str, pagina, fragmento: str) -> None:
    """Interruptor que muestra la página del PDF donde está la cita (solo se dibuja si se enciende)."""
    pdf = st.session_state.get("pdf_bytes")
    if pdf and pagina and st.toggle(f"👁️ Ver la página {pagina} del documento", key=f"ver_{clave}"):
        png, resaltado = _pagina_img(pdf, int(pagina), fragmento or "")
        st.image(png, use_container_width=True,
                 caption="Cita resaltada en amarillo." if resaltado else
                 "Página del documento (es un escaneo: no se puede resaltar el texto; búscalo en esta página).")


def _kpi(etiqueta, valor, color="az", sub=""):
    st.markdown(f'<div class="kpi {color}"><div class="et">{html.escape(etiqueta)}</div>'
                f'<div class="val">{html.escape(str(valor))}</div>'
                f'<div class="sub">{html.escape(sub) or "&nbsp;"}</div></div>', unsafe_allow_html=True)


def _caja(titulo, d, icono="", color="az", largo=380):
    """Un dato con su cita: cuadro de color con el texto, y la evidencia plegada debajo."""
    if not d.valor:
        cuerpo, pie = "<i>No aparece en el documento.</i>", ""
    else:
        txt = d.valor if len(d.valor) <= largo else d.valor[:largo].rsplit(" ", 1)[0] + "…"
        estado = "✅ cita verificada" if d.verificado else "⚠️ cita no verificada"
        cuerpo, pie = _resaltar(txt), f'<div class="pie">📄 página {d.pagina} · {estado}</div>'
    st.markdown(f'<div class="caja {color}"><div class="tit">{icono} {html.escape(titulo)}</div>'
                f'<div class="txt">{cuerpo}</div>{pie}</div>', unsafe_allow_html=True)
    if d.valor:
        with st.expander("Ver texto completo y cita"):
            st.write(d.valor)
            st.markdown(f"> {d.fragmento}")
            _ver_pagina(titulo, d.pagina, d.fragmento)


# ---------- Registro del Banco de Inversiones (barra lateral) ----------
st.sidebar.markdown("### Registro del Banco de Inversiones")
st.sidebar.caption("Opcional: completa el CUI y permite contrastar el documento con el registro oficial.")
reg_demo = sorted(glob.glob("data/demo/registros/*.pdf"))
reg_choice = st.sidebar.selectbox("Registro de ejemplo", ["(ninguno)"] + [os.path.basename(f) for f in reg_demo])
reg_up = st.sidebar.file_uploader("...o sube el registro (PDF)", type=["pdf"], key="reg")
registro = None
try:
    if reg_up:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tf.write(reg_up.getvalue())
        registro = parse_bi(tf.name)
    elif reg_choice != "(ninguno)":
        registro = parse_bi(os.path.join("data/demo/registros", reg_choice))
except Exception as e:
    st.sidebar.error(f"No pude leer el registro: {e}")
_usos = st.session_state.get("usos", [])
if _usos:
    _c = _llm.costo_usd(_usos)
    st.sidebar.markdown("### Consumo de esta sesión")
    st.sidebar.caption(f"{len(_usos)} llamadas al modelo · {sum(r['entrada'] for r in _usos):,} tokens de entrada · "
                       f"{sum(r['salida'] for r in _usos):,} de salida"
                       + (f" · ≈ US$ {_c:.3f} a precio de lista" if _c is not None else ""))
st.sidebar.markdown("---")
st.sidebar.markdown("### Corpus normativo")
try:
    from src.rag import corpus_info, sistemas_disponibles
    _info = corpus_info()
except Exception:
    _info = {}
if _info:
    _ETIQ = {"invierte": "Invierte.pe", "presupuesto": "Presupuesto", "planeamiento": "Planeamiento",
             "contrataciones": "Contrataciones"}
    sistemas_sel = st.sidebar.multiselect(
        "Sistemas que se consultan", sistemas_disponibles(), default=["invierte"],
        format_func=lambda s: _ETIQ.get(s, s))
    st.sidebar.caption(f"{_info['n_normas']} normas · {_info['n_fragmentos']:,} fragmentos · "
                       f"indexado el {_info['construido']}. Verifica siempre la vigencia en El Peruano.")
else:
    sistemas_sel = ["invierte"]
    st.sidebar.caption("Aún no hay índice normativo (corre `python -m src.rag build`).")

# ---------- 1. Documento ----------
demo_files = sorted(glob.glob("data/demo/*.pdf"))
col_a, col_b = st.columns(2)
choice = col_a.selectbox("Documento de ejemplo", ["(ninguno)"] + [os.path.basename(f) for f in demo_files])
uploaded = col_b.file_uploader("...o sube un PDF", type=["pdf"])

doc_name, pages = None, None
if uploaded:
    doc_name = uploaded.name
    key = ("up", uploaded.name, uploaded.size)
    if st.session_state.get("doc_key") != key:
        barra = st.progress(0.0, text="Leyendo documento (usa la caché si ya fue procesado)...")
        t_ini = time.time()

        def _avance(i, n, ocr):
            seg = time.time() - t_ini
            barra.progress(i / n, text=f"Leyendo página {i} de {n}" + (" con OCR (las páginas escaneadas tardan)" if ocr else "")
                           + f" · {seg:.0f} s")
        try:
            st.session_state.pdf_bytes = uploaded.getvalue()
            st.session_state.pages = extract_pages_from_bytes(uploaded.getvalue(), progreso=_avance)
        except Exception as e:
            st.session_state.pages = None
            st.error(f"No pude leer el documento: {e}")
        barra.empty()
        st.session_state.doc_key, st.session_state.matrix = key, None
elif choice != "(ninguno)":
    doc_name = choice
    key = ("demo", choice)
    if st.session_state.get("doc_key") != key:
        with st.spinner("Leyendo documento..."):
            with open(os.path.join("data/demo", choice), "rb") as _f:
                st.session_state.pdf_bytes = _f.read()
            st.session_state.pages = extract_pages(os.path.join("data/demo", choice))
        st.session_state.doc_key, st.session_state.matrix = key, None
pages = st.session_state.get("pages") if doc_name else None

if pages:
    n_ocr = sum(p["ocr"] for p in pages)
    st.success(f"{doc_name}: {len(pages)} páginas ({n_ocr} leídas con OCR).")

    if st.button("Extraer matriz", type="primary"):
        with st.spinner(f"Extrayendo datos con citas de {len(pages)} páginas... suele tardar entre 20 y 60 segundos. "
                        "El modelo responde de una sola vez, por eso no hay barra de avance."):
            try:
                _n0 = len(_llm.USO)
                st.session_state.matrix = extract_matrix(pages)
                st.session_state.uso_extraccion = list(_llm.USO[_n0:])
                st.session_state.setdefault("usos", []).extend(_llm.USO[_n0:])
            except KeyError:
                st.error("Falta la clave del modelo: completa LLM_API_KEY y LLM_MODEL en tu .env.")
            except Exception as e:
                st.error(f"Error al extraer: {e}")
    m = st.session_state.get("matrix")

    tab_res, tab_dash, tab_con, tab_tabla, tab_chat = st.tabs(
        ["Resumen", "Dashboard", "Contraste", "Tabla completa", "Preguntas"])

    # ---------- Resumen ----------
    with tab_res:
        if not m:
            st.info("Pulsa **Extraer matriz** para generar el resumen del proyecto.")
        else:
            cui = m.cui.valor or ((registro or {}).get("cui") or {}).get("valor")
            st.header(m.nombre_proyecto.valor or "Proyecto sin nombre")
            st.caption(f"CUI **{cui or '—'}**  ·  {m.entidad.valor or '—'}  ·  {m.ubicacion.valor or '—'}")
            k = kpis(m, registro)
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                _kpi("Inversión", _soles(k["inversion"]), "az", k["fuente_inversion"] or "")
            with c2:
                _kpi("Beneficiarios", f"{k['beneficiarios']:,}" if k["beneficiarios"] else "—", "vd")
            with c3:
                _kpi("Costo por beneficiario", _soles(k["costo_por_beneficiario"]), "az", "Inversión ÷ beneficiarios")
            with c4:
                _kpi("Brecha del servicio", f"{k['brecha_pct']:.0f}%" if k["brecha_pct"] is not None else "—", "vd")
            st.write("")
            st.download_button("⬇️  Descargar matriz en Excel",
                               data=matriz_a_excel(m, registro, doc_name or ""),
                               file_name=f"{os.path.splitext(doc_name or 'matriz')[0]}_matriz.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
            ex = st.session_state.get("uso_extraccion")
            _c = _llm.costo_usd(ex) if ex else None
            st.caption(f"Citas verificadas: {k['n_verificadas']} de {k['n_citas']}."
                       + (f" Procesar este documento: {sum(r['entrada'] for r in ex):,} tokens de entrada y "
                          f"{sum(r['salida'] for r in ex):,} de salida"
                          + (f" ≈ US$ {_c:.3f} a precio de lista." if _c is not None else ".") if ex else ""))
            al = alertas(m, registro)
            n_rev = sum(1 for nivel, _ in al if nivel in ("error", "aviso"))
            with st.expander(f"🚦 Alertas de revisión · {n_rev}", expanded=n_rev > 0):
                if not al:
                    st.success("Sin alertas: las citas se verificaron y coincide con el registro.")
                for nivel, texto in al:
                    st.markdown({"error": "🔴", "aviso": "🟠", "info": "🔵"}[nivel] + " " + texto)
            col_a, col_b = st.columns(2)
            with col_a:
                _caja("Problema central", m.problema_central, "❗", "az")
                _caja("Brecha", m.brecha, "📉", "vd")
            with col_b:
                _caja("Objetivo", m.objetivo, "🎯", "vd")
                _caja("Población beneficiaria", m.poblacion_beneficiaria, "👥", "az")
            if m.componentes:
                items = "".join(f"<li>{html.escape(c.valor or '')} "
                                f"<small>· pág. {c.pagina} {'✅' if c.verificado else '⚠️'}</small></li>"
                                for c in m.componentes)
                st.markdown(f'<div class="caja az"><div class="tit">🧩 Componentes</div>'
                            f'<div class="txt"><ul style="margin:0;padding-left:1.2rem">{items}</ul></div></div>',
                            unsafe_allow_html=True)

    # ---------- Dashboard ----------
    with tab_dash:
        if not m:
            st.info("Pulsa **Extraer matriz** para ver el dashboard.")
        else:
            k = kpis(m, registro)
            filas = costos_tabla(m)
            if not filas:
                st.info("No se encontraron partidas de costo en el documento.")
            else:
                df_c = pd.DataFrame(filas)
                total = df_c["Monto (S/)"].sum()
                df_c["Parte"] = df_c["Monto (S/)"] / total
                _limpio = [re.sub(r"\s*\(\d+(?:[\.,]\d+)?\s*%\)\s*$", "", str(p)) for p in df_c["Partida"]]
                df_c["Etiqueta"] = [f"{p} ({x:.0%})" for p, x in zip(_limpio, df_c["Parte"])]
                inv = k["inversion"]
                top = df_c.iloc[0]
                top3 = df_c["Parte"].head(3).sum()
                n_ver = int((df_c["Verificado"] == "✅").sum())
                nombre_top = str(top["Partida"])
                nombre_top = nombre_top if len(nombre_top) <= 70 else nombre_top[:67] + "…"
                izq, der = st.columns([1, 2])
                with izq:
                    _kpi("Mayor partida", _soles(top["Monto (S/)"]), "az", f"{top['Parte']:.0%} de lo leído · {nombre_top}")
                    st.write("")
                    _kpi("Concentración", f"{top3:.0%}", "vd", f"Las 3 partidas mayores, de {len(df_c)} leídas")
                    st.write("")
                    _kpi("Cobertura de partidas", f"{total / inv:.0%}" if inv else "—", "az",
                         f"S/ {total:,.0f} leídos de la inversión total" if inv else "Sin inversión de referencia")
                    st.write("")
                    _kpi("Partidas respaldadas", f"{n_ver} de {len(df_c)}", "vd", "Con cita y monto hallados en la página")
                with der:
                    st.markdown("**¿En qué se va la inversión?**")
                    forma = st.radio("Gráfico", ["Dona", "Barras"], horizontal=True, label_visibility="collapsed")
                    paleta = ["#2f6fed", "#1f9d6b", "#7aa7f7", "#7fd1ae", "#f2b84b", "#e9758a", "#9b8cf0", "#4fb3bf",
                              "#c9d6ef", "#b6e3cb", "#f7d9a0", "#f2b3be"]
                    tip = ["Partida", alt.Tooltip("Monto (S/):Q", format=",.2f"),
                           alt.Tooltip("Parte:Q", format=".1%", title="% de lo leído"), "Página"]
                    escala = alt.Scale(domain=list(df_c["Etiqueta"]), range=paleta[:len(df_c)])
                    if forma == "Dona":
                        chart = (alt.Chart(df_c).mark_arc(innerRadius=85, outerRadius=150)
                                 .encode(theta=alt.Theta("Monto (S/):Q", stack=True),
                                         color=alt.Color("Etiqueta:N", scale=escala, legend=None),
                                         tooltip=tip).properties(height=340))
                    else:
                        chart = (alt.Chart(df_c).mark_bar(color="#2f6fed")
                                 .encode(x=alt.X("Monto (S/):Q", title="Soles"),
                                         y=alt.Y("Partida:N", sort="-x", title=None, axis=alt.Axis(labelLimit=380)), tooltip=tip)
                                 .properties(height=max(240, 36 * len(df_c))))
                    st.altair_chart(chart, use_container_width=True)
                    if forma == "Dona":
                        leyenda = "".join(
                            f"<div style='display:flex;gap:8px;align-items:flex-start;margin:3px 0;font-size:.85rem;line-height:1.3'>"
                            f"<span style='flex:none;width:11px;height:11px;border-radius:50%;margin-top:4px;background:{paleta[i % len(paleta)]}'></span>"
                            f"<span>{html.escape(e)}</span></div>" for i, e in enumerate(df_c["Etiqueta"]))
                        st.markdown(f"<div style='padding:4px 8px'>{leyenda}</div>", unsafe_allow_html=True)
                st.caption("Los porcentajes son sobre lo leído. Si la cobertura es baja, el documento no lista todas las partidas; "
                           "si pasa de 100%, puede haber subtotales repetidos.")
                with st.expander("Ver tabla de partidas"):
                    st.dataframe(df_c, hide_index=True, use_container_width=True,
                                 column_order=["Partida", "Monto (S/)", "Parte", "Página", "Verificado"],
                                 column_config={"Monto (S/)": st.column_config.NumberColumn(format="%.2f"),
                                                "Parte": st.column_config.NumberColumn("% de lo leído", format="percent")})

            if m.indicadores:
                st.write("")
                st.markdown("**Indicadores del proyecto**")
                filas_i = "".join(
                    f"<tr><td>{html.escape(str(i.nombre))}</td><td class='num'>{html.escape(str(i.valor))}</td>"
                    f"<td class='num'>{i.pagina if i.pagina is not None else '—'}</td>"
                    f"<td class='num'>{'✅' if i.verificado else '⚠️'}</td></tr>" for i in m.indicadores)
                st.markdown("<table class='tabla'><thead><tr><th>Indicador</th><th>Valor</th><th>Pág.</th><th></th></tr></thead>"
                            f"<tbody>{filas_i}</tbody></table>", unsafe_allow_html=True)

    # ---------- Contraste ----------
    with tab_con:
        if not m:
            st.info("Pulsa **Extraer matriz** primero.")
        elif not registro:
            st.info("Elige o sube un registro del Banco de Inversiones en la barra lateral para contrastar.")
        else:
            st.markdown("Compara lo que dice el documento técnico con lo registrado oficialmente.")
            st.dataframe(pd.DataFrame(contrastar(m, registro)), use_container_width=True, hide_index=True)

    # ---------- Tabla completa ----------
    with tab_tabla:
        if m:
            df = pd.DataFrame(completar_con_registro(matrix_rows(m), registro))
            df["verificado"] = df["verificado"].map({True: "✅", False: "⚠️ no verificado",
                                                     "registro": "📋 del registro", None: ""})
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_order=["campo", "valor", "página", "fragmento", "verificado"])
        pg = st.number_input("Ver el texto de una página", 1, len(pages), 1)
        with st.expander(f"Página {pg}"):
            st.text(pages[pg - 1]["text"])
        _ver_pagina("tabla", pg, "")

    # ---------- Chat ----------
    with tab_chat:
        st.caption("Responde con el documento cargado y con la normativa, citando página y artículo. "
                   "Si no hay evidencia, lo dice.")
        _SUG = {"Componentes y costos": "¿Cuáles son los componentes del proyecto y cuánto cuesta cada uno?",
                "Vigencia de la viabilidad": "¿Cuál es la vigencia de la declaración de viabilidad?",
                "Modificar la cartera del PMI": "¿Cómo se modifica la cartera de inversiones del PMI?",
                "Tipo de ficha técnica": "¿Qué tipo de ficha técnica corresponde según el monto de inversión?"}
        st.markdown("**Prueba con una pregunta:**")
        _cols = st.columns(len(_SUG))
        for _i, (_c, (_et, _preg)) in enumerate(zip(_cols, _SUG.items())):
            _c.button(_et, key=f"sug{_i}", use_container_width=True, help=_preg,
                      on_click=lambda s=_preg: st.session_state.update(pregunta_sug=s))
        hist = st.session_state.setdefault("chat", [])
        for h in hist:
            with st.chat_message(h["role"]):
                st.write(h["texto"])
                for f in h.get("fuentes", []):
                    st.caption(f"{'✅' if f['verificado'] else '⚠️'} {f['etiqueta']} — “{f['fragmento']}”")
        q = st.chat_input("Pregunta sobre el documento o la normativa") or st.session_state.pop("pregunta_sug", None)
        if q:
            hist.append({"role": "user", "texto": q})
            st.chat_message("user").write(q)
            with st.chat_message("assistant"):
                with st.spinner("Buscando en el documento y en las normas..."):
                    try:
                        from src.rag import answer
                        _n0 = len(_llm.USO)
                        r = answer(q, pages, sistemas_sel)
                        st.session_state.setdefault("usos", []).extend(_llm.USO[_n0:])
                        st.write(r["texto"])
                        for f in r["fuentes"]:
                            st.caption(f"{'✅' if f['verificado'] else '⚠️'} {f['etiqueta']} — “{f['fragmento']}”")
                        hist.append({"role": "assistant", "texto": r["texto"], "fuentes": r["fuentes"]})
                    except KeyError:
                        st.error("Falta la clave del modelo: completa LLM_API_KEY y LLM_MODEL en tu .env.")
                    except FileNotFoundError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Error al responder: {e}")
else:
    st.info("Elige un documento de ejemplo o sube un PDF para empezar.")
