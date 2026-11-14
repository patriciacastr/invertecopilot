# Costo por documento

Medición real con el documento de prueba (resumen ejecutivo escaneado, Pitumarca):

| Concepto | Valor |
|---|---|
| Tokens de entrada | 31,993 |
| Tokens de salida (incluye razonamiento del modelo) | 6,342 |
| Modelo | gemini-3.5-flash |
| Precio de lista de entrada | US$ 1.50 por millón |
| Precio de lista de salida | US$ 9.00 por millón |
| **Costo por documento** | **≈ US$ 0.105** |

Cálculo: 31,993 / 1,000,000 × 1.50 + 6,342 / 1,000,000 × 9.00 = 0.048 + 0.057.

## Supuestos y límites
- Precios de lista tomados de agregadores que citan la documentación de Google; **`[VERIFICAR en la página oficial de precios de Gemini antes de entregar]`**.
- Un documento de 28 páginas debería costar menos; uno más largo, más. El costo crece con las páginas enviadas al modelo.
- No incluye el costo de las preguntas del chat (cada pregunta envía fragmentos numerados, pocos miles de tokens); `[MEDIR en la barra lateral «Consumo de esta sesión» y anotar]`.
- No incluye servidor: Streamlit Community Cloud es gratuito para una demo.
- El OCR corre localmente (sin costo por llamada) y queda en caché.

## Ejemplo de margen
Un usuario con 40 documentos al mes: 40 × 0.105 ≈ US$ 4.2 de extracción.
