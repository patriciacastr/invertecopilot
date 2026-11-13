"""InvierteCopilot - app principal (Streamlit).

Flujo:
  1. Subir PDF de ficha técnica / estudio.
  2. Extraer texto por página (OCR si es escaneado).
  3. Extraer matriz estructurada con cita de página.
  4. Chat: responde desde el documento y/o desde el corpus normativo.
"""
import streamlit as st

from src.ocr import extract_pages
from src.extract import extract_matrix
from src.rag import answer

st.set_page_config(page_title="InvierteCopilot", layout="wide")
st.title("InvierteCopilot")
st.caption("Asistente para revisar fichas técnicas de Invierte.pe, con citas de página y de norma.")

uploaded = st.file_uploader("Sube una ficha técnica o estudio (PDF)", type=["pdf"])

if uploaded:
    if st.session_state.get("doc_name") != uploaded.name:
        with st.spinner("Leyendo documento (OCR si hace falta)..."):
            st.session_state.pages = extract_pages(uploaded.getvalue())
            st.session_state.doc_name = uploaded.name
            st.session_state.matrix = None

    tab1, tab2 = st.tabs(["Matriz del proyecto", "Preguntas"])

    with tab1:
        if st.button("Extraer matriz"):
            with st.spinner("Extrayendo datos con citas..."):
                st.session_state.matrix = extract_matrix(st.session_state.pages)
        if st.session_state.get("matrix"):
            st.dataframe(st.session_state.matrix, use_container_width=True)

    with tab2:
        q = st.chat_input("Pregunta sobre el documento o la normativa")
        if q:
            st.chat_message("user").write(q)
            st.chat_message("assistant").write(answer(q, st.session_state.pages))
else:
    q = st.chat_input("Pregunta sobre teoría o normativa de Invierte.pe")
    if q:
        st.chat_message("user").write(q)
        st.chat_message("assistant").write(answer(q, pages=None))

st.sidebar.markdown("**Corpus normativo:** *(fecha de corte: completar)*")
