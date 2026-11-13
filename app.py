"""InvierteCopilot - app principal (Streamlit).

Flujo: elegir o subir un PDF -> texto por página (caché/OCR) -> matriz con citas verificadas
-> chat (documento + normativa).
Para correr:  streamlit run app.py
"""
import glob
import os

import pandas as pd
import streamlit as st

from src.extract import extract_matrix, matrix_rows
from src.ocr import extract_pages, extract_pages_from_bytes

st.set_page_config(page_title="InvierteCopilot", layout="wide")
st.title("InvierteCopilot")
st.caption("Asistente para revisar fichas técnicas de Invierte.pe, con citas de página y de norma.")

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

    tab1, tab2 = st.tabs(["Matriz del proyecto", "Preguntas"])

    # ---------- 2. Matriz ----------
    with tab1:
        if st.button("Extraer matriz"):
            with st.spinner("Extrayendo datos con citas..."):
                try:
                    st.session_state.matrix = extract_matrix(pages)
                except KeyError:
                    st.error("Falta la clave del modelo: completa LLM_API_KEY y LLM_MODEL en tu .env.")
                except Exception as e:
                    st.error(f"Error al extraer: {e}")
        m = st.session_state.get("matrix")
        if m:
            df = pd.DataFrame(matrix_rows(m))
            df["verificado"] = df["verificado"].map({True: "✅", False: "⚠️ no verificado", None: ""})
            st.dataframe(df, use_container_width=True, hide_index=True)
            if m.informacion_faltante:
                st.warning("Información faltante: " + "; ".join(m.informacion_faltante))
            pg = st.number_input("Ver el texto de la página", 1, len(pages), 1)
            with st.expander(f"Página {pg}"):
                st.text(pages[pg - 1]["text"])

    # ---------- 3. Chat ----------
    with tab2:
        q = st.chat_input("Pregunta sobre el documento o la normativa")
        if q:
            st.chat_message("user").write(q)
            try:
                from src.rag import answer
                st.chat_message("assistant").write(answer(q, pages))
            except NotImplementedError:
                st.chat_message("assistant").write("El chat normativo se activa cuando carguemos el corpus (src/rag.py).")
else:
    st.info("Elige un documento de ejemplo o sube un PDF para empezar.")

st.sidebar.markdown("**Corpus normativo:** *(fecha de corte: pendiente)*")
