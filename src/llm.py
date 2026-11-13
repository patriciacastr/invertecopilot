"""Un solo punto de contacto con el modelo de lenguaje.

Proveedor por defecto: Gemini (Google AI Studio, clave gratuita).
Variables de .env:
    LLM_PROVIDER=gemini
    LLM_API_KEY=...
    LLM_MODEL=gemini-3.6-flash

Dos funciones públicas:
    structured(system, user, schema) -> instancia de un modelo pydantic (JSON validado)
    generate_text(system, user)      -> str (respuestas del chat)

Por qué pedimos el JSON en el prompt y lo validamos nosotros con pydantic:
funciona igual con cualquier proveedor y, si el modelo devuelve algo inválido,
reintentamos una vez con el error.
"""
import json
import os
import re
import time
from typing import Type

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

MAX_OUTPUT_TOKENS = 8192   # Gemini 3.x gasta tokens en "pensar" antes de responder: dejamos margen


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").lower()


def _call(system: str, user: str, json_mode: bool) -> str:
    """Llama al proveedor y devuelve el texto de la respuesta."""
    key, model = os.environ["LLM_API_KEY"], os.environ["LLM_MODEL"]
    if _provider() == "gemini":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        # Si el modelo está saturado (503) o con límite (429): espera y reintenta,
        # y al final prueba el modelo de respaldo (LLM_FALLBACK_MODEL).
        modelos = [model] + ([os.environ["LLM_FALLBACK_MODEL"]] if os.environ.get("LLM_FALLBACK_MODEL") else [])
        ultimo = None
        for m in modelos:
            for intento in range(3):
                try:
                    resp = client.models.generate_content(model=m, contents=user, config=cfg)
                    return resp.text or ""
                except Exception as e:  # noqa: BLE001
                    ultimo = e
                    texto = str(e)
                    if any(c in texto for c in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED")):
                        time.sleep(2 * (intento + 1))
                        continue
                    raise
        raise ultimo
    if _provider() == "anthropic":
        import anthropic

        msg = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=MAX_OUTPUT_TOKENS, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
    raise ValueError(f"LLM_PROVIDER no soportado: {_provider()}")


def generate_text(system: str, user: str) -> str:
    return _call(system, user, json_mode=False).strip()


def _extract_json(text: str) -> str:
    """Quita cercos ```json ... ``` si el modelo los puso."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def structured(system: str, user: str, schema: Type[BaseModel]) -> BaseModel:
    esquema = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    sistema = (f"{system}\n\nResponde SOLO con un objeto JSON válido (sin texto extra) "
               f"que cumpla este esquema:\n{esquema}")
    ultimo_error = None
    for intento in range(2):
        pedido = user if intento == 0 else (
            f"{user}\n\nTu respuesta anterior no fue válida ({ultimo_error}). "
            "Devuelve únicamente el JSON corregido.")
        texto = _call(sistema, pedido, json_mode=True)
        try:
            return schema.model_validate_json(_extract_json(texto))
        except ValidationError as e:
            ultimo_error = str(e)[:300]
    raise ValueError(f"El modelo no devolvió JSON válido: {ultimo_error}")
