import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["LLM_API_KEY"])

excluir = ("tts", "live", "image", "audio", "embedding", "transcribe", "robotics", "omni", "banana")
nombres = [m.name.replace("models/", "") for m in client.models.list()]
candidatos = [n for n in nombres if "flash" in n and not any(x in n for x in excluir)]
print("Modelos flash disponibles:", candidatos)

# Primero el modelo de tu .env, luego los demás (máximo 6 llamadas en total)
elegido = os.environ.get("LLM_MODEL", "")
orden = ([elegido] if elegido else []) + [n for n in candidatos if n != elegido]

for n in orden[:6]:
    try:
        r = client.models.generate_content(model=n, contents="Responde solo: ok")
        print("FUNCIONA:", n, "->", (r.text or "").strip()[:20])
    except Exception as e:
        print("FALLA:   ", n, "->", str(e)[:100])
