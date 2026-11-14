# Arquitectura

```mermaid
flowchart TD
    U[Consultor] -->|sube PDF| A[app.py · Streamlit]
    A --> O[src/ocr.py<br/>PyMuPDF + OCR Tesseract/Paddle<br/>caché por hash del PDF]
    O -->|texto por página| E[src/extract.py]
    E -->|prompt + esquema| L[src/llm.py<br/>Gemini Flash · respaldo Flash-Lite<br/>reintentos · consumo]
    L -->|JSON| E
    E -->|verifica fragmento en la página| M[(Matriz con citas)]
    R[Registro Banco de Inversiones<br/>src/parse_bi.py] --> C[src/contraste.py]
    M --> C
    M --> D[src/dashboard.py · src/alertas.py<br/>cifras por código]
    M --> X[src/exportar.py · Excel]
    C --> A
    D --> A
    X --> A
    Q[Pregunta del usuario] --> G[src/rag.py]
    N[(Índice BM25<br/>data/index)] --> G
    M -. páginas del documento .-> G
    G -->|fragmentos numerados| L
    L -->|respuesta con citas literales| G
    G -->|verifica citas · se abstiene si no hay respaldo| A
```

## Principios
1. **El modelo lee, el código verifica y calcula.** Toda cita se comprueba contra el texto de la página; todo monto derivado lo calcula código.
2. **Abstención antes que invención.** Si la cobertura de la consulta es baja, el chat dice que no encontró respaldo.
3. **Caché.** El OCR se guarda por contenido del PDF: se paga una vez por documento.
4. **Corpus normativo versionado.** Cada norma tiene sistema, tipo y si está derogada (`data/corpus/manifest.csv`); las derogadas pesan menos al ordenar.
