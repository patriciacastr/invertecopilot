# Costo por documento

Medición real con el documento de prueba (resumen ejecutivo escaneado, Pitumarca):

| Concepto | Valor |
|---|---|
| Tokens de entrada | 31,993 |
| Tokens de salida (incluye razonamiento del modelo) | 6,342 |
| Modelo | gemini-3.5-flash |
| Precio de lista de entrada | US$ 1.50 por millón |
| Precio de lista de salida | US$ 9.00 por millón |
| **Costo por documento** | **≈ US$ 0.105** (Flash, precio de lista de terceros) |
| Mismo uso con Flash-Lite (precio oficial verificado: US$ 0.30 / US$ 2.50 por millón) | ≈ US$ 0.025 |

Cálculo: 31,993 / 1,000,000 × 1.50 + 6,342 / 1,000,000 × 9.00 = 0.048 + 0.057.

## Supuestos y límites
- Precios de lista tomados de agregadores que citan la documentación de Google (consultados el 14/11/2026); **`[VERIFICAR en https://ai.google.dev/gemini-api/docs/pricing antes de entregar y anotar la fecha]`**.
- **Aviso sobre el modelo:** según las notas de versión de Google (8/10/2026), `gemini-3.5-flash` está obsoleto y sus solicitudes se redirigen automáticamente a `gemini-3.6-flash`; el endpoint no se apaga. No pude confirmar qué precio se factura en ese caso, así que el costo de arriba es una cota superior razonable al precio de 3.5. `[REVISAR en el panel de uso de AI Studio qué modelo y qué costo aparece realmente]`
- Un documento de 28 páginas debería costar menos; uno más largo, más. El costo crece con las páginas enviadas al modelo.
- No incluye el costo de las preguntas del chat (cada pregunta envía fragmentos numerados, pocos miles de tokens); `[MEDIR en la barra lateral «Consumo de esta sesión» y anotar]`.
- No incluye servidor: Streamlit Community Cloud es gratuito para una demo.
- El OCR corre localmente (sin costo por llamada) y queda en caché.

## Ejemplo de margen
Un equipo de 5 a 8 personas con 2 o 3 documentos al mes cada una procesa de 10 a 24 documentos: 10 × 0.105 ≈ US$ 1.05 y 24 × 0.105 ≈ US$ 2.52 de extracción al mes, a precio de lista de gemini-3.5-flash. No incluye las preguntas del chat ni el servidor.
