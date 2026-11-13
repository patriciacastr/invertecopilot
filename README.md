# InvierteCopilot

> **One-liner:** Hacemos un asistente para consultores de inversión pública que convierte una ficha técnica en una matriz verificada, con citas de página y de norma, mediante OCR y RAG sobre la normativa de Invierte.pe.

*(Borrador: ajústalo cuando termines las conversaciones con usuarios.)*

---

## 1. One-liner
Hacemos **[X]** para **[Y]** mediante **[Z]**.

## 2. Founder
- **Patricia Castro Hilario** — estudiante de Economía (Universidad del Pacífico), con experiencia en consultoría de inversión pública (Invierte.pe).
- Por qué soy la persona indicada: *(completa: qué hiciste, qué documentos revisaste, qué te frustró)*.

## 3. Problema
- **Quién lo sufre:** consultores y equipos técnicos que revisan fichas técnicas y estudios de preinversión.
- **Cuánto cuesta:** *(horas por documento × costo hora; completa con lo que te digan en las entrevistas)*.
- **Cómo se resuelve hoy:** lectura manual y matrices en Excel.
- **Evidencia:** notas de 3 conversaciones en [`docs/research/`](docs/research/).

## 4. Solución e insight
*(Qué hace el producto y cuál es el insight: no es un resumidor de PDF, es un extractor con trazabilidad y contraste normativo.)*

## 5. Why now
*(OCR de documentos abierto + LLMs con salida estructurada + RAG hacen viable lo que antes requería analistas leyendo cada PDF.)*

## 6. Demo
- **URL pública:** *(pendiente)*
- **Correr en local:**
  ```bash
  pip install -r requirements.txt
  cp .env.example .env   # agrega tu clave
  streamlit run app.py
  ```
- **Capturas:** *(3 capturas en `docs/img/`)*
- **Arquitectura:** ver `docs/arquitectura.md`
- **Modelos/APIs y por qué:** *(completa)*

## 7. Modelo de negocio
- **Quién paga:** consultoras y equipos técnicos de inversión pública.
- **Precio:** *(ej. S/ X por usuario/mes)*
- **Costo por usuario:** tokens por documento × documentos al mes + servidor. *(calcúlalo con `docs/costos.md`)*

## 8. Herramientas del curso
| Herramienta | Sesión | Archivo |
|---|---|---|
| Document AI con PaddleOCR | 10 | `src/ocr.py` |
| LLMs con salidas estructuradas y RAG | 08 | `src/extract.py`, `src/rag.py` |

## 9. Qué hizo el agente
*(Lista qué partes generó Claude Code y qué escribiste/entendiste tú.)*

---
### Opcional
Mercado (TAM/SAM/SOM), competencia, primeros usuarios, roadmap, riesgos.
