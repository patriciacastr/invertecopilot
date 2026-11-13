"""Un solo punto de contacto con el LLM (salida estructurada).

Cambia SOLO esta función si usas otro proveedor que el de la sesión 08.
Variables: LLM_API_KEY, LLM_MODEL (ver .env.example).
"""
import os
from typing import Type
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


def structured(system: str, user: str, schema: Type[BaseModel]) -> BaseModel:
    """Devuelve una instancia de `schema` (tool use con el JSON schema de pydantic)."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["LLM_API_KEY"])
    tool = {"name": "registrar", "description": "Registra los datos extraídos.",
            "input_schema": schema.model_json_schema()}
    msg = client.messages.create(
        model=os.environ["LLM_MODEL"], max_tokens=4096, system=system,
        tools=[tool], tool_choice={"type": "tool", "name": "registrar"},
        messages=[{"role": "user", "content": user}],
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    return schema.model_validate(block.input)
