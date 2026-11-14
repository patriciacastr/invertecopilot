"""Chat con dos fuentes: el documento cargado + el corpus normativo de Invierte.pe.

Herramienta del curso: LLMs + RAG (sesión 08).

Cómo funciona (todo se puede explicar en la exposición):
  1. build_index(): lee los PDF de data/corpus según data/corpus/manifest.csv, limpia el texto de
     El Peruano, lo parte en fragmentos (~1200 caracteres) y guarda metadatos: norma, página, artículo.
  2. retrieve(): búsqueda léxica BM25 sobre esos fragmentos (+ filtro por sistema normativo).
     Si ningún fragmento cubre lo que se pregunta, NO se llama al modelo: se responde que no hay evidencia.
  3. answer(): el modelo redacta SOLO con los fragmentos recuperados y cita el id de cada uno con un
     texto literal; el código verifica que ese texto esté de verdad en el fragmento citado.

Uso desde la terminal:
  python -m src.rag build        # reconstruye data/index/corpus_index.json.gz
  python -m src.rag eval         # mide la recuperación con eval/preguntas.csv
  python -m src.rag "¿qué es el CUI?"   # prueba una consulta (solo recuperación)
"""
import csv
import gzip
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

CORPUS_DIR = "data/corpus"
MANIFEST = os.path.join(CORPUS_DIR, "manifest.csv")
INDEX_PATH = "data/index/corpus_index.json.gz"

CHUNK_CHARS = 1200
OVERLAP_CHARS = 150
MIN_COBERTURA = 0.55     # fracción de los términos de la pregunta que debe aparecer en el mejor fragmento
K_NORMA, K_DOC = 6, 4
PENALIZA_DEROGADA = 0.7

STOP = set("""de la el en y a los las del que se por un una con para al lo es su sus o como mas pero
este esta estos estas ese esa son ser sea han hay ha le les ya sin sobre entre cuando donde cual cuales
que quien segun todo todos toda todas tambien si no ni muy puede pueden debe deben tiene tienen cada
hacer hace esto eso aquel""".split())


ACRONIMOS = {   # las normas definen las siglas con su nombre completo: se agrega a la consulta
    "ioarr": "inversiones de optimización ampliación marginal reposición rehabilitación",
    "cui": "código único de inversiones",
    "pmi": "programa multianual de inversiones",
    "opmi": "oficina de programación multianual de inversiones",
    "dgpmi": "dirección general de programación multianual de inversiones",
    "uf": "unidad formuladora",
    "uei": "unidad ejecutora de inversiones",
    "ei": "expediente técnico",
    "pip": "proyecto de inversión",
    "snpmgi": "sistema nacional de programación multianual y gestión de inversiones",
    "bi": "banco de inversiones",
    "fte": "ficha técnica estándar",
    "pei": "proyecto especial de inversión",
}

SISTEMA_DEFECTO = ["invierte"]   # el corpus incluye presupuesto, planeamiento y contrataciones, pero no por defecto


def expandir(consulta: str) -> str:
    extra = [v for k, v in ACRONIMOS.items() if re.search(rf"\b{k}\b", consulta.lower())]
    return consulta + " " + " ".join(extra) if extra else consulta


# ---------------------------------------------------------------- texto
def _sin_tildes(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def tokens(texto: str) -> List[str]:
    """Minúsculas, sin tildes, sin palabras vacías; las palabras se reducen a su raíz (6 letras)."""
    out = []
    for w in re.findall(r"[a-z0-9]+", _sin_tildes(texto).lower()):
        if w in STOP or len(w) < 2:
            continue
        out.append(w if w.isdigit() else w[:6])
    return out


def limpiar(texto: str) -> str:
    """Arregla ruido típico de los PDF de El Peruano."""
    t = texto.replace("ﬁ ", "fi").replace("ﬂ ", "fl").replace("ﬁ", "fi").replace("ﬂ", "fl")
    t = re.sub(r"(?m)^\s*\d{0,3}\s*NORMAS LEGALES\s*$", "", t)
    t = re.sub(r"(?m)^\s*(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[aá]bado|Domingo) \d{1,2} de \w+ de \d{4}\s*/?\s*$", "", t)
    t = re.sub(r"(?m)^\s*/?\s*El Peruano\s*$", "", t)
    t = re.sub(r"Esta es una copia aut[eé]ntica imprimible[^\n]*(\n[^\n]*){0,2}", "", t)
    t = re.sub(r"-\n(?=[a-záéíóúñ])", "", t)          # palabras cortadas al final de línea
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


ART_RE = re.compile(r"(?m)^\s*(?:“|\")?\s*(Art[ií]culo\s+\d+[\w\-º°]*)\s*[\.\-–:]")


def _partir(texto: str) -> List[str]:
    """Parte un texto en bloques de ~CHUNK_CHARS respetando saltos de párrafo/oración."""
    texto = re.sub(r"\s*\n\s*", " ", texto).strip()
    if len(texto) <= CHUNK_CHARS:
        return [texto] if texto else []
    out, i = [], 0
    while i < len(texto):
        j = min(i + CHUNK_CHARS, len(texto))
        if j < len(texto):
            corte = max(texto.rfind(". ", i, j), texto.rfind("; ", i, j))
            if corte > i + CHUNK_CHARS * 0.5:
                j = corte + 1
        out.append(texto[i:j].strip())
        if j >= len(texto):
            break
        i = max(j - OVERLAP_CHARS, i + 1)
    return out


# ---------------------------------------------------------------- índice
def build_index(corpus_dir: str = CORPUS_DIR, out_path: str = INDEX_PATH) -> Dict:
    import fitz
    filas = [r for r in csv.DictReader(open(os.path.join(corpus_dir, "manifest.csv"), encoding="utf-8"))
             if r["incluir"].strip() == "1"]
    chunks, resumen = [], []
    for r in filas:
        ruta = os.path.join(corpus_dir, r["archivo"])
        if not os.path.exists(ruta):
            print("  (falta)", r["archivo"])
            continue
        art_actual, n_doc = "", 0
        doc = fitz.open(ruta)
        for num, pagina in enumerate(doc, 1):
            texto = limpiar(pagina.get_text())
            if len(texto) < 40:
                continue
            # el artículo vigente en cada punto del texto (se arrastra de una página a otra)
            marcas = [(m.start(), m.group(1)) for m in ART_RE.finditer(texto)]
            for frag in _partir(texto):
                pos = texto.find(frag[:60].split(". ")[0][:40])
                art = art_actual
                for p_, a_ in marcas:
                    if pos >= 0 and p_ <= pos:
                        art = a_
                m_in = ART_RE.search(frag)
                if m_in:
                    art = m_in.group(1)
                chunks.append({"id": f"{len(chunks)}", "archivo": r["archivo"], "norma": r["norma"],
                               "sistema": r["sistema"], "nota": r["nota"], "pagina": num,
                               "articulo": art.replace("Articulo", "Artículo"), "texto": frag})
                n_doc += 1
            if marcas:
                art_actual = marcas[-1][1]
        resumen.append((r["norma"], len(doc), n_doc))
    meta = {"construido": date.today().isoformat(), "n_normas": len(resumen), "n_fragmentos": len(chunks),
            "chunk_chars": CHUNK_CHARS}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump({"meta": meta, "chunks": chunks}, f, ensure_ascii=False)
    for n, p, c in resumen:
        print(f"  {n[:70]:70} {p:4} pág  {c:4} fragmentos")
    print(f"Índice: {meta['n_normas']} normas, {meta['n_fragmentos']} fragmentos -> {out_path}")
    return meta


class BM25:
    """BM25 clásico. Cada doc: dict con 'texto' y opcionalmente 'norma' (el título también cuenta)."""

    def __init__(self, docs: List[Dict], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.tf = [Counter(tokens((d.get("norma", "") + " ") * 1 + d["texto"])) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.post = defaultdict(list)
        for i, c in enumerate(self.tf):
            for t in c:
                self.post[t].append(i)

    def buscar(self, consulta: str, k: int = 5, permitido=None) -> List[Dict]:
        q = list(dict.fromkeys(tokens(consulta)))
        if not q:
            return []
        scores = defaultdict(float)
        for t in q:
            if t not in self.idf:
                continue
            for i in self.post[t]:
                f = self.tf[i][t]
                den = f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg)
                scores[i] += self.idf[t] * f * (self.k1 + 1) / den
        res = []
        for i, s in sorted(scores.items(), key=lambda x: -x[1]):
            if permitido and not permitido(self.docs[i]):
                continue
            cobertura = sum(1 for t in q if t in self.tf[i]) / len(q)
            res.append({**self.docs[i], "score": round(s, 2), "cobertura": round(cobertura, 2)})
            if len(res) == k:
                break
        return res


_CACHE: Dict = {}


def _indice() -> Optional[Dict]:
    if "bm25" not in _CACHE:
        if not os.path.exists(INDEX_PATH):
            return None
        with gzip.open(INDEX_PATH, "rt", encoding="utf-8") as f:
            data = json.load(f)
        _CACHE["meta"], _CACHE["bm25"] = data["meta"], BM25(data["chunks"])
    return _CACHE


def corpus_info() -> Dict:
    """Metadatos del índice (fecha de corte, cantidad de normas) para mostrar en la app."""
    ind = _indice()
    return ind["meta"] if ind else {}


def sistemas_disponibles() -> List[str]:
    ind = _indice()
    return sorted({d["sistema"] for d in ind["bm25"].docs}) if ind else []


def retrieve_norma(query: str, k: int = K_NORMA, sistemas: Optional[List[str]] = None) -> List[Dict]:
    ind = _indice()
    if not ind:
        raise FileNotFoundError("Falta data/index/corpus_index.json.gz: corre  python -m src.rag build")
    sistemas = sistemas or SISTEMA_DEFECTO
    res = ind["bm25"].buscar(expandir(query), k * 3, lambda d: d["sistema"] in sistemas)
    for c in res:                       # una norma derogada compite con desventaja frente a la vigente
        if "derog" in (c.get("nota") or "").lower():
            c["score"] = round(c["score"] * PENALIZA_DEROGADA, 2)
    return sorted(res, key=lambda c: -c["score"])[:k]


def retrieve_doc(query: str, pages: List[Dict], k: int = K_DOC) -> List[Dict]:
    docs = []
    for p in pages:
        for frag in _partir(limpiar(p["text"])):
            docs.append({"pagina": p["page"], "texto": frag})
    return BM25(docs).buscar(expandir(query), k) if docs else []


# ---------------------------------------------------------------- respuesta
class CitaLLM(BaseModel):
    id: str = Field(..., description="Id del fragmento citado, como N1 o D2")
    fragmento: str = Field(..., description="Texto LITERAL corto (máx. 25 palabras) copiado de ese fragmento")


class RespuestaLLM(BaseModel):
    respuesta: str = Field(..., description="Respuesta en español, con marcas [N1], [D2] tras cada afirmación")
    citas: List[CitaLLM] = Field(default_factory=list)
    suficiente: bool = Field(..., description="False si los fragmentos no bastan para responder")


SYSTEM = (
    "Eres un asistente para consultores de inversión pública en Perú (Invierte.pe). "
    "Responde SOLO con los fragmentos numerados que se te entregan: [Nx] son normas y [Dx] el documento "
    "del proyecto. No uses conocimiento externo. Después de cada afirmación pon la marca del fragmento, "
    "por ejemplo [N2]. Si los fragmentos no bastan, devuelve suficiente=false y di qué falta. "
    "Si una norma está marcada como derogada o desactualizada, advierte que hay que verificar la vigente. "
    "Para cada cita copia un fragmento LITERAL corto (máx. 25 palabras). Responde breve y concreto."
)


def _etiqueta(c: Dict) -> str:
    if "norma" in c:
        art = f", {c['articulo']}" if c.get("articulo") else ""
        return f"{c['norma']}{art}, p. {c['pagina']}"
    return f"Documento, p. {c['pagina']}"


def answer(question: str, pages: Optional[List[Dict]] = None, sistemas: Optional[List[str]] = None,
           llm=None) -> Dict:
    """Devuelve {'texto', 'fuentes', 'abstuvo'}. Cada fuente trae etiqueta, página, fragmento y 'verificado'."""
    from src.extract import fragment_in_page

    normas = retrieve_norma(question, K_NORMA, sistemas) if _indice() else []
    docs = retrieve_doc(question, pages, K_DOC) if pages else []
    normas = [c for c in normas if c["cobertura"] >= MIN_COBERTURA]
    docs = [c for c in docs if c["cobertura"] >= MIN_COBERTURA]
    if not normas and not docs:
        return {"texto": "No encontré evidencia suficiente en el documento ni en el corpus normativo cargado. "
                         "Prueba reformular la pregunta con términos de la norma (por ejemplo, el nombre de "
                         "la directiva o del procedimiento).", "fuentes": [], "abstuvo": True}

    ctx, ref = [], {}
    for i, c in enumerate(docs, 1):
        ref[f"D{i}"] = c
        ctx.append(f"[D{i}] (Documento del proyecto, página {c['pagina']})\n{c['texto']}")
    for i, c in enumerate(normas, 1):
        ref[f"N{i}"] = c
        aviso = " [OJO: " + c["nota"] + "]" if c.get("nota") else ""
        ctx.append(f"[N{i}] ({_etiqueta(c)}){aviso}\n{c['texto']}")
    if llm is None:
        from src.llm import structured as llm
    r = llm(SYSTEM, "FRAGMENTOS:\n\n" + "\n\n".join(ctx) + f"\n\nPREGUNTA: {question}", RespuestaLLM)

    fuentes = []
    for c in r.citas:
        base = ref.get(c.id.strip("[] "))
        if not base:
            continue
        fuentes.append({"id": c.id, "etiqueta": _etiqueta(base), "pagina": base["pagina"],
                        "fragmento": c.fragmento,
                        "tipo": "norma" if "norma" in base else "documento",
                        "verificado": fragment_in_page(c.fragmento, base["texto"])})
    texto = r.respuesta
    for k, base in ref.items():                       # [N1] -> [Directiva..., art. 5, p. 12]
        texto = texto.replace(f"[{k}]", f"[{_etiqueta(base)}]")
    return {"texto": texto, "fuentes": fuentes, "abstuvo": not r.suficiente}


# ---------------------------------------------------------------- evaluación y CLI
def evaluar(path: str = "eval/preguntas.csv", k: int = K_NORMA) -> None:
    """Para cada pregunta: ¿la norma esperada aparece entre los k mejores fragmentos? Y las preguntas
    fuera de alcance (esperada vacía): ¿el sistema se abstiene?"""
    filas = list(csv.DictReader(open(path, encoding="utf-8")))
    aciertos = abst_ok = n_con = n_sin = 0
    for f in filas:
        res = [c for c in retrieve_norma(f["pregunta"], k) if c["cobertura"] >= MIN_COBERTURA]
        if f["archivo_esperado"].strip():
            n_con += 1
            ok = any(c["archivo"] in f["archivo_esperado"].split("|") for c in res)
            aciertos += ok
            print(("✅" if ok else "❌"), f["pregunta"][:70], "->", (res[0]["norma"][:45] if res else "—"))
        else:
            n_sin += 1
            ok = not res
            abst_ok += ok
            print(("✅" if ok else "❌"), "[fuera de alcance]", f["pregunta"][:60],
                  "->", "se abstiene" if ok else res[0]["norma"][:45])
    print(f"\nRecuperación (norma esperada en top-{k}): {aciertos}/{n_con}")
    print(f"Abstención correcta en preguntas fuera de alcance: {abst_ok}/{n_sin}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        build_index()
    elif len(sys.argv) > 1 and sys.argv[1] == "eval":
        evaluar()
    elif len(sys.argv) > 1:
        for c in retrieve_norma(" ".join(sys.argv[1:])):
            print(c["score"], c["cobertura"], _etiqueta(c), "\n   ", c["texto"][:200].replace("\n", " "))
    else:
        print(__doc__)
