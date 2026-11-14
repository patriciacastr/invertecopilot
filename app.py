"""InvierteCopilot - app principal (Streamlit).

Flujo: elegir o subir un PDF -> texto por página (caché/OCR) -> matriz con citas verificadas
-> chat (documento + normativa).
Para correr:  streamlit run app.py
"""
import glob
import os

import pandas as pd
import streamlit as st

import tempfile

import altair as alt

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


def _tarjeta(titulo, d, icono="", largo=420):
    """Un dato con su cita: texto legible arriba, evidencia plegada abajo."""
    with st.container(border=True):
        st.markdown(f"**{icono} {titulo}**")
        if not d.valor:
            st.caption("No aparece en el documento.")
            return
        txt = d.valor if len(d.valor) <= largo else d.valor[:largo].rsplit(" ", 1)[0] + "…"
        st.write(txt)
        estado = "✅ cita verificada" if d.verificado else "⚠️ cita no verificada"
        st.caption(f"📄 página {d.pagina} · {estado}")
        with st.expander("Ver texto completo y cita"):
            st.write(d.valor)
            st.markdown(f"> {d.fragmento}")


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
        with st.spinner("Leyendo documento (usa la caché si ya fue procesado)..."):
            try:
                st.session_state.pages = extract_pages_from_bytes(uploaded.getvalue())
            except Exception as e:
                st.session_state.pages = None
                st.error(f"No pude leer el documento: {e}")
        st.session_state.doc_key, st.session_state.matrix = key, None
elif choice != "(ninguno)":
    doc_name = choice
    key = ("demo", choice)
    if st.session_state.get("doc_key") != key:
        with st.spinner("Leyendo documento..."):
            st.session_state.pages = extract_pages(os.path.join("data/demo", choice))
        st.session_state.doc_key, st.session_state.matrix = key, None
pages = st.session_state.get("pages") if doc_name else None

if pages:
    n_ocr = sum(p["ocr"] for p in pages)
    st.success(f"{doc_name}: {len(pages)} páginas ({n_ocr} leídas con OCR).")

    if st.button("Extraer matriz", type="primary"):
        with st.spinner("Extrayendo datos con citas..."):
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
            c1.metric("Inversión", _soles(k["inversion"]), help=k["fuente_inversion"])
            c2.metric("Beneficiarios", f"{k['beneficiarios']:,}" if k["beneficiarios"] else "—")
            c3.metric("Costo por beneficiario", _soles(k["costo_por_beneficiario"]),
                      help="Inversión / beneficiarios, calculado por código")
            c4.metric("Brecha del servicio", f"{k['brecha_pct']:.0f}%" if k["brecha_pct"] is not None else "—")
            st.caption(f"Inversión según: {k['fuente_inversion'] or '—'}. "
                       f"Citas verificadas: {k['n_verificadas']} de {k['n_citas']}.")
            ex = st.session_state.get("uso_extraccion")
            if ex:
                _c = _llm.costo_usd(ex)
                st.caption(f"Procesar este documento: {sum(r['entrada'] for r in ex):,} tokens de entrada y "
                           f"{sum(r['salida'] for r in ex):,} de salida"
                           + (f" ≈ US$ {_c:.3f} a precio de lista." if _c is not None else "."))
            st.download_button("⬇️ Descargar matriz en Excel",
                               data=matriz_a_excel(m, registro, doc_name or ""),
                               file_name=f"{os.path.splitext(doc_name or 'matriz')[0]}_matriz.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            col_a, col_b = st.columns(2)
            with col_a:
                _tarjeta("Problema central", m.problema_central, "❗")
                _tarjeta("Brecha", m.brecha, "📉")
            with col_b:
                _tarjeta("Objetivo", m.objetivo, "🎯")
                _tarjeta("Población beneficiaria", m.poblacion_beneficiaria, "👥")
            if m.componentes:
                with st.container(border=True):
                    st.markdown("**🧩 Componentes**")
                    for c in m.componentes:
                        st.markdown(f"- {c.valor}  \n  <small>📄 pág. {c.pagina} · "
                                    f"{'✅' if c.verificado else '⚠️'}</small>", unsafe_allow_html=True)
            faltante = list(m.informacion_faltante)
            if cui:
                faltante = [f for f in faltante if f.strip().lower() != "cui"]
            if faltante:
                st.warning("No aparece en el documento: " + "; ".join(faltante))

    # ---------- Dashboard ----------
    with tab_dash:
        if not m:
            st.info("Pulsa **Extraer matriz** para ver el dashboard.")
        else:
            k = kpis(m, registro)
            d1, d2 = st.columns([1, 2])
            with d1:
                st.markdown("**Brecha de servicio**")
                if k["brecha_pct"] is not None:
                    st.progress(min(k["brecha_pct"], 100) / 100, text=f"{k['brecha_pct']:.0f}% sin cubrir")
                else:
                    st.caption("El documento no trae un porcentaje de brecha.")
                st.metric("Inversión", _soles(k["inversion"]), help=k["fuente_inversion"])
                st.metric("Costo por beneficiario", _soles(k["costo_por_beneficiario"]))
            with d2:
                st.markdown("**¿En qué se va la inversión?**")
                filas = costos_tabla(m)
                if filas:
                    df_c = pd.DataFrame(filas)
                    chart = (alt.Chart(df_c).mark_bar(color="#2f6fed")
                             .encode(x=alt.X("Monto (S/):Q", title="Soles"),
                                     y=alt.Y("Partida:N", sort="-x", title=None),
                                     tooltip=["Partida", alt.Tooltip("Monto (S/):Q", format=",.2f"), "Página"])
                             .properties(height=max(120, 34 * len(df_c))))
                    st.altair_chart(chart, use_container_width=True)
                    st.caption("Partidas leídas del documento (con página); pueden no sumar el total "
                               "si el documento no las lista completas.")
                    with st.expander("Ver tabla de partidas"):
                        st.dataframe(df_c, hide_index=True, use_container_width=True,
                                     column_config={"Monto (S/)": st.column_config.NumberColumn(format="%.2f")})
                else:
                    st.info("No se encontraron partidas de costo en el documento.")
            if m.indicadores:
                st.markdown("**Indicadores del proyecto**")
                df_i = pd.DataFrame([{"Indicador": i.nombre, "Valor": i.valor, "Página": i.pagina,
                                      "Verificado": "✅" if i.verificado else "⚠️"} for i in m.indicadores])
                st.dataframe(df_i, hide_index=True, use_container_width=True)

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

    # ---------- Chat ----------
    with tab_chat:
        st.caption("Responde con el documento cargado y con la normativa, citando página y artículo. "
                   "Si no hay evidencia, lo dice.")
        hist = st.session_state.setdefault("chat", [])
        for h in hist:
            with st.chat_message(h["role"]):
                st.write(h["texto"])
                for f in h.get("fuentes", []):
                    st.caption(f"{'✅' if f['verificado'] else '⚠️'} {f['etiqueta']} — “{f['fragmento']}”")
        q = st.chat_input("Pregunta sobre el documento o la normativa")
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
