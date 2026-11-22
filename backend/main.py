import math
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

import chromadb
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "legal_book_chunks")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

LLM_API_KEY = (os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or ("https://api.groq.com/openai/v1" if LLM_API_KEY else "")
).strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or "openai/gpt-oss-120b").strip()
LLM_FALLBACK_MODELS = [
    m.strip()
    for m in (os.getenv("LLM_FALLBACK_MODELS") or "llama-3.3-70b-versatile,openai/gpt-oss-20b").split(",")
    if m.strip()
]
last_llm_error: str = ""

SHORT_DISCLAIMER = (
    "Disclaimer: For prototype informational purposes only; not formal legal advice. "
    "This is only for general guidance, not professional legal support."
)

OUT_OF_SCOPE_MSG = (
    "This question is outside the scope of my indexed legal corpus or is not clearly answered in the provided excerpts. "
    "My current knowledge base only includes the Constitution of the Islamic Republic of Pakistan (1973) and the Code of Criminal Procedure (CrPC 1898)—other laws (such as the Pakistan Penal Code or civil statutes) are not indexed here."
)

BUSY_MSG = "The answer service is temporarily busy. Please send your question again in a few seconds."

CONST_NAME = "Constitution of the Islamic Republic of Pakistan, 1973"
CRPC_NAME = "Code of Criminal Procedure (CrPC), 1898"

STOP_WORDS = {
    "what", "is", "the", "a", "an", "of", "in", "on", "for", "to", "and",
    "or", "how", "when", "where", "why", "who", "can", "should", "does",
    "do", "are", "was", "were", "be", "been", "with", "from", "by", "under",
    "this", "that", "these", "those", "it", "its", "as", "at", "into",
    "someone", "person", "they", "them", "their",
}

app = FastAPI(title="Legal AI Advisor ChromaDB Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model: Optional[SentenceTransformer] = None
collection = None
corpus_docs: List[dict] = []
chunk_map: Dict[Tuple[str, int], dict] = {}
idf_scores: Dict[str, float] = {}
avg_doc_len: float = 1.0


class ChatRequest(BaseModel):
    query: str
    language: Optional[str] = "english"


class ChatResponse(BaseModel):
    reply: str
    reference: Optional[str] = None
    disclaimer: str = SHORT_DISCLAIMER


def clean_text(raw: str) -> str:
    text = re.sub(r"\[Page\s+\d+\]\s*", " ", raw or "")
    text = re.sub(r"Page\s+\d+\s+of\s+\d+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def book_kind(book_title: str) -> str:
    t = (book_title or "").lower()
    if "constitution" in t:
        return "constitution"
    if "criminal" in t or "crpc" in t or "procedure" in t:
        return "crpc"
    return "other"


def book_display(kind: str, title: str) -> str:
    if kind == "constitution":
        return CONST_NAME
    if kind == "crpc":
        return CRPC_NAME
    return title


def normalize_reply_formatting(text: str) -> str:
    """Enforce clean formatting: bold headings and provisions only, no #, >, ---, or trailing citation lists."""
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*(.+?)\s*$", r"**\1**", text)
    cleaned = re.sub(r"(?m)^\s*>\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", cleaned)
    cleaned = re.sub(r"(?<!\*)\*((?:Article|Section)\s+[^*\n]+?)\*(?!\*)", r"**\1**", cleaned)
    cleaned = re.sub(r"\(\s*(\*\*)?((?:Article|Section)\s+[^()\n]+?)(\*\*)?\s*\)", r"**\2**", cleaned)
    cleaned = re.sub(r"\*\*+", "**", cleaned)
    cleaned = re.sub(r"\n+\*\*Citations?\*\*[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if len(t) >= 2 and t not in STOP_WORDS]


def build_bm25_index():
    """Load all chunks from ChromaDB once at startup for Hybrid (Dense + BM25) retrieval."""
    global corpus_docs, idf_scores, avg_doc_len, chunk_map
    if collection is None:
        return

    all_data = collection.get(include=["documents", "metadatas"])
    ids = all_data.get("ids") or []
    docs = all_data.get("documents") or []
    metas = all_data.get("metadatas") or []

    corpus_docs = []
    chunk_map = {}
    df_counter: Counter = Counter()
    total_len = 0

    for i, doc_id in enumerate(ids):
        raw_doc = docs[i] if i < len(docs) else ""
        if not raw_doc:
            continue
        meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
        cleaned = clean_text(raw_doc)
        toks = tokenize(cleaned)
        tf = Counter(toks)
        total_len += len(toks)
        for term in tf.keys():
            df_counter[term] += 1

        entry = {
            "id": doc_id,
            "book_title": meta.get("book_title", "Legal Reference"),
            "chunk_index": safe_int(meta.get("chunk_index", 0)),
            "provisions": str(meta.get("provisions") or ""),
            "cleaned": cleaned,
            "tf": tf,
            "doc_len": len(toks),
        }
        corpus_docs.append(entry)
        chunk_map[(entry["book_title"], entry["chunk_index"])] = entry

    n_docs = max(len(corpus_docs), 1)
    avg_doc_len = max(total_len / n_docs, 1.0)
    idf_scores = {
        term: math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        for term, df in df_counter.items()
    }
    print(
        f"Loaded {len(corpus_docs)} chunks into Hybrid BM25+Vector index. "
        f"LLM enabled: {bool(LLM_API_KEY and LLM_BASE_URL)} ({LLM_MODEL})"
    )


@app.on_event("startup")
def startup_event():
    global model, collection
    model = SentenceTransformer(EMBED_MODEL_NAME)
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    build_bm25_index()


def embed_query(text: str) -> List[float]:
    if model is None:
        raise RuntimeError("Embedding model is not initialized.")
    emb = model.encode([text], normalize_embeddings=True)[0]
    arr = np.asarray(emb, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def bm25_search(query: str, top_k: int = 25) -> Dict[str, dict]:
    q_tokens = tokenize(query)
    if not q_tokens or not corpus_docs:
        return {}

    bigrams = [" ".join(q_tokens[i:i + 2]) for i in range(len(q_tokens) - 1)]
    trigrams = [" ".join(q_tokens[i:i + 3]) for i in range(len(q_tokens) - 2)]

    k1 = 1.5
    b = 0.75
    scored = []

    for doc in corpus_docs:
        score = 0.0
        tf = doc["tf"]
        dl = doc["doc_len"]
        for term in q_tokens:
            f = tf.get(term, 0)
            if f == 0:
                continue
            idf = idf_scores.get(term, 0.0)
            denom = f + k1 * (1.0 - b + b * (dl / avg_doc_len))
            score += idf * ((f * (k1 + 1.0)) / denom)

        lower_text = doc["cleaned"].lower()
        for bg in bigrams:
            if bg in lower_text:
                score += 1.5
        for tg in trigrams:
            if tg in lower_text:
                score += 3.0

        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    max_s = scored[0][0] if scored and scored[0][0] > 0 else 1.0

    results = {}
    for s, doc in scored[:top_k]:
        results[doc["id"]] = {**doc, "bm25_norm": s / max_s}
    return results


def llm_enabled() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY)


def expand_query(query: str) -> List[str]:
    """Translate an everyday-language question into the formal legal wording used in the books."""
    if not llm_enabled():
        return []
    system = (
        "You help search the Constitution of Pakistan (1973) and the Code of Criminal Procedure (1898). "
        "Rewrite the user's everyday question as 5 short search queries (max 16 words each). Queries 1-3 must use the "
        "formal legal vocabulary and the section/article HEADING wording those books use (for example: 'safeguards as to "
        "arrest and detention', 'protection against self-incrimination', 'protection against retrospective punishment', "
        "'mode of searching women', 'search of place entered by person sought to be arrested'). Queries 4-5 must be written "
        "as the likely WORDING of the legal rule itself, in the style of an old statute (for example: 'the search shall be "
        "made by another woman with strict regard to decency'). Cover different legal angles. "
        "Output exactly 5 lines, one query per line, no numbering, no explanations."
    )
    out = call_llm(system, query, 600)
    if not out:
        return []
    lines = []
    for ln in out.splitlines():
        ln = re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip()
        if 3 <= len(ln) <= 200:
            lines.append(ln)
    return lines[:5]


def hybrid_retrieve(queries: List[str], top_k: int = 7, wide: bool = False) -> List[dict]:
    """Hybrid (vector + BM25) retrieval over the user's question plus its legal-vocabulary rewrites."""
    if collection is None or model is None:
        raise RuntimeError("Retrieval dependencies are not initialized.")

    if collection.count() != len(corpus_docs):
        build_bm25_index()

    original = queries[0]
    q_lower = original.lower()
    vec_res = collection.query(
        query_embeddings=[embed_query(q) for q in queries],
        n_results=25,
        include=["documents", "metadatas", "distances"],
    )

    candidates: Dict[str, dict] = {}
    for qi in range(len(queries)):
        ids = (vec_res.get("ids") or [])[qi] if qi < len(vec_res.get("ids") or []) else []
        docs = (vec_res.get("documents") or [])[qi]
        metas = (vec_res.get("metadatas") or [])[qi]
        dists = (vec_res.get("distances") or [])[qi]
        for idx, doc_id in enumerate(ids):
            doc = docs[idx] if idx < len(docs) else ""
            if not doc:
                continue
            meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
            dist = dists[idx] if idx < len(dists) and dists[idx] is not None else 1.0
            vec_sim = max(0.0, 1.0 - float(dist))
            weight = 1.0 if qi == 0 else 0.97
            vec_sim *= weight
            if doc_id in candidates:
                if vec_sim > candidates[doc_id]["vec_score"]:
                    candidates[doc_id]["vec_score"] = vec_sim
                    candidates[doc_id]["vec_real"] = vec_sim
                continue
            candidates[doc_id] = {
                "id": doc_id,
                "book_title": meta.get("book_title", "Legal Reference"),
                "chunk_index": safe_int(meta.get("chunk_index", 0)),
                "provisions": str(meta.get("provisions") or ""),
                "cleaned": clean_text(doc),
                "vec_score": vec_sim,
                "vec_real": vec_sim,
                "bm25_norm": 0.0,
            }

    for qi, q in enumerate(queries):
        weight = 1.0 if qi == 0 else 0.85
        for doc_id, hit in bm25_search(q, top_k=25).items():
            norm = hit["bm25_norm"] * weight
            if doc_id in candidates:
                candidates[doc_id]["bm25_norm"] = max(candidates[doc_id]["bm25_norm"], norm)
            else:
                candidates[doc_id] = {
                    "id": doc_id,
                    "book_title": hit["book_title"],
                    "chunk_index": hit["chunk_index"],
                    "provisions": hit["provisions"],
                    "cleaned": hit["cleaned"],
                    "vec_score": 0.25,
                    "vec_real": 0.0,
                    "bm25_norm": norm,
                }

    ranked = []
    for item in candidates.values():
        combined = 0.55 * item["vec_score"] + 0.45 * item["bm25_norm"]
        lower = item["cleaned"].lower()
        if (
            "preamble" not in q_lower
            and "objectives resolution" not in q_lower
            and ("now, therefore, we, the people of pakistan" in lower or "delegated to the state of pakistan" in lower)
        ):
            combined -= 0.25
        item["final_score"] = combined
        ranked.append(item)

    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    if not ranked:
        return []

    best_vec = max((r["vec_real"] for r in ranked), default=0.0)
    top_score = ranked[0]["final_score"]
    top_book = ranked[0]["book_title"]

    selected: List[dict] = []
    for item in ranked:
        if len(selected) >= top_k:
            break
        if item["book_title"] != top_book and item["final_score"] < (0.35 if wide else 0.6) * top_score:
            continue
        selected.append(item)

    selected_keys = {(s["book_title"], s["chunk_index"]) for s in selected}
    extras: List[dict] = []
    for item in selected[: (4 if wide else 2)]:
        for delta in (-1, 1):
            key = (item["book_title"], item["chunk_index"] + delta)
            if key in chunk_map and key not in selected_keys:
                nb = chunk_map[key]
                extras.append({
                    "id": nb["id"],
                    "book_title": nb["book_title"],
                    "chunk_index": nb["chunk_index"],
                    "provisions": nb["provisions"],
                    "cleaned": nb["cleaned"],
                    "vec_score": 0.0,
                    "vec_real": 0.0,
                    "bm25_norm": 0.0,
                    "final_score": 0.0,
                })
                selected_keys.add(key)

    final = selected + extras
    final.sort(key=lambda x: (x["book_title"], x["chunk_index"]))
    for p in final:
        p["best_vec"] = best_vec
    return final


def is_detailed_query(query: str) -> bool:
    q = (query or "").lower()
    detail_triggers = [
        "detail", "details", "detailed", "explain", "elaborate", "comprehensive",
        "list all", "what are all", "all rights", "step by step", "steps",
        "procedure", "in depth", "thorough",
    ]
    return any(trigger in q for trigger in detail_triggers)


def find_provision_passage(num: str, kind: str, passages: List[dict]) -> Optional[dict]:
    """Return the retrieved chunk that really contains this Article/Section (heading preferred), else None."""
    want_const = kind == "constitution"
    pat_heading = re.compile(rf"(?<![\d/,\-])\b{re.escape(num)}\s?\.\s*[A-Z\"“(\[]")
    pat_ref = re.compile(rf"\b(?:Article|Section|article|section)s?\s+{re.escape(num)}\b")
    ref_hit = None
    for p in passages:
        if (book_kind(p["book_title"]) == "constitution") != want_const:
            continue
        if pat_heading.search(p["cleaned"]):
            return p
        if ref_hit is None and pat_ref.search(p["cleaned"]):
            ref_hit = p
    return ref_hit


def extract_citations(reply: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for m in re.finditer(r"\b(Article|Section)\s+(\d{1,3}[A-Z]?)\b", reply):
        item = ("constitution" if m.group(1) == "Article" else "crpc", m.group(2))
        if item not in out:
            out.append(item)
    return out


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
    """Calls the primary model; on rate limits/errors automatically tries the fallback models."""
    global last_llm_error
    last_llm_error = ""
    models = [LLM_MODEL] + [m for m in LLM_FALLBACK_MODELS if m != LLM_MODEL]

    for model_name in models:
        body = {
            "model": model_name,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if "gpt-oss" in model_name.lower():
            body["reasoning_effort"] = "low"

        for attempt in range(2):
            try:
                with httpx.Client(timeout=45.0) as client:
                    resp = client.post(
                        f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {LLM_API_KEY}",
                        },
                        json=body,
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
                    content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                    if content:
                        return content
                    last_llm_error = f"{model_name}: empty content (token limit?)"
                    print(last_llm_error)
                    break
                last_llm_error = f"{model_name} HTTP {resp.status_code}: {resp.text[:300]}"
                print(f"LLM API error -> {last_llm_error}")
                if resp.status_code in (429, 500, 502, 503) and attempt == 0:
                    try:
                        wait = float(resp.headers.get("retry-after", "2"))
                    except ValueError:
                        wait = 2.0
                    if wait <= 6:
                        time.sleep(max(wait, 1.0))
                        continue
                break
            except Exception as exc:
                last_llm_error = f"{model_name} request failed: {exc}"
                print(last_llm_error)
                if attempt == 0:
                    time.sleep(1.0)
                    continue
                break
    return None


def build_reference(reply_text: str, passages: List[dict]) -> Optional[str]:
    """Reference lines are built ONLY from provisions the answer cites and that really exist in the retrieved text."""
    refs = []
    for kind, num in extract_citations(reply_text):
        p = find_provision_passage(num, kind, passages)
        if p:
            label = "Article" if kind == "constitution" else "Section"
            title = re.sub(r"\.pdf$", "", p["book_title"], flags=re.IGNORECASE)
            refs.append(f"{title} - {label} {num}")
    refs = list(dict.fromkeys(refs))
    return " | ".join(refs[:4]) if refs else None


def generate_with_llm(query: str, passages: List[dict]) -> dict:
    """Returns {"status": "ok"|"out"|"error", "reply": str, "reference": Optional[str]}."""
    if not llm_enabled():
        print(f"LLM skipped: LLM_BASE_URL={bool(LLM_BASE_URL)}, LLM_API_KEY={bool(LLM_API_KEY)}")
        return {"status": "error", "reply": BUSY_MSG, "reference": None}

    detailed = is_detailed_query(query)
    max_tokens = 1800 if detailed else 1200

    context_blocks = []
    for idx, p in enumerate(passages, start=1):
        kind = book_kind(p["book_title"])
        label = "Articles" if kind == "constitution" else "Sections"
        context_blocks.append(
            f"[Excerpt {idx} | {book_display(kind, p['book_title'])} | numbered provisions here are {label}]\n{p['cleaned']}"
        )
    context_text = "\n\n".join(context_blocks)

    rules = (
        "You are a Pakistani Legal AI Assistant. Always respond strictly in English. "
        "You may use ONLY the excerpts provided, which come from the Constitution of the Islamic Republic of "
        "Pakistan (1973) and the Code of Criminal Procedure (CrPC 1898).\n"
        "1. UNDERSTAND EVERYDAY WORDING: users are ordinary people. Match their question to the excerpts by LEGAL MEANING, "
        "not by exact words (for example being punished under a new law for an old act is a question about retrospective "
        "punishment; being forced to confess is a question about self-incrimination and torture; a male officer searching a "
        "woman is a question about the mode of searching women). Questions may be tricky, hypothetical or ask about an "
        "exception. If any excerpt contains the rule that governs the situation, you MUST answer from it: state what the "
        "provision says and, if the text states no exception or alternative, say that the provision gives none.\n"
        "2. STRICT GROUNDING: every statement must be supported by the excerpts. Never use outside knowledge and never "
        "guess. Output ONLY the exact token OUT_OF_SCOPE when NO excerpt contains any rule about the subject of the "
        "question (for example it is about Pakistan Penal Code offences/punishments, contracts, or general knowledge). "
        "Read ALL excerpts carefully before deciding; do not choose OUT_OF_SCOPE if any excerpt is relevant.\n"
        "3. CORRECT PROVISIONS: attribute to a provision ONLY what its own text says. Never move the content of one "
        "Section/Article onto another number. Cite a number ONLY if its heading (for example '12. Protection against ...') "
        "or a direct reference to it appears in the excerpts. The Constitution uses Articles; the CrPC uses Sections. "
        "Never cite excerpt numbers. Write each provision separately (**Section 47** and **Section 48**, never 'Sections 47 and 48'). "
        "Do not cite a provision that does not support your answer.\n"
        "4. COMPLETENESS: include the conditions, provisos and exceptions that matter. Do not mention irrelevant provisions.\n"
        "5. CITATION STYLE: no parenthetical citations. Write the provision in **bold** inside the sentence, for example "
        "**Section 48 of the Code of Criminal Procedure (CrPC)** or **Article 12 of the Constitution of Pakistan**. "
        "You may add a clause such as 13(b) only when it clearly matches the text.\n"
        "6. FORMAT: ONLY plain text and **bold**. NEVER use '#', blockquotes, '---', italics, or a citations list.\n"
    )
    if detailed:
        rules += (
            "7. STRUCTURE (use exactly these bold headings):\n**Most Relevant**\nThe single most relevant provision in bold "
            "with a clear explanation (3-4 sentences) in simple English.\n**Supported Articles**\nOther relevant provisions in "
            "bold, each with a short explanation of how it relates. If there are none, write: No other directly relevant provision found."
        )
    else:
        rules += (
            "7. LENGTH: short, clear and direct in simple English (3-5 sentences). Start with 'Yes.' or 'No.' (or "
            "'Generally, no.') for yes/no questions ('Can...', 'Does...', 'Is...'), then explain with the exact provision."
        )

    user_prompt = f"Excerpts:\n{context_text}\n\nQuestion: {query}"

    reply_text = ""
    for attempt in range(2):
        content = call_llm(rules, user_prompt, max_tokens)
        if not content:
            return {"status": "error", "reply": BUSY_MSG, "reference": None}
        if "OUT_OF_SCOPE" in content[:80]:
            return {"status": "out", "reply": OUT_OF_SCOPE_MSG, "reference": None}

        reply_text = normalize_reply_formatting(content)
        bad = [
            f"{'Article' if k == 'constitution' else 'Section'} {n}"
            for k, n in extract_citations(reply_text)
            if find_provision_passage(n, k, passages) is None
        ]
        if not bad:
            break
        user_prompt = (
            f"Excerpts:\n{context_text}\n\nQuestion: {query}\n\n"
            f"WARNING: your previous answer cited {', '.join(bad)}, which does NOT appear in the excerpts. "
            "Answer again citing only provisions whose number actually appears in the excerpts and describe each "
            "provision only by what its own text says."
        )

    return {"status": "ok", "reply": reply_text, "reference": build_reference(reply_text, passages)}


@app.get("/health")
def health_check():
    count = collection.count() if collection is not None else 0
    return {
        "status": "ok",
        "version": "v6-llm-fallback",
        "collection": COLLECTION_NAME,
        "indexed_chunks": count,
        "llm_enabled": bool(LLM_API_KEY and LLM_BASE_URL),
        "llm_model": LLM_MODEL if (LLM_API_KEY and LLM_BASE_URL) else None,
        "env_file_loaded": ENV_PATH.exists(),
    }


@app.get("/llm-test")
def llm_test():
    """Open this URL in a browser to see whether the AI service (Groq) is working, and the exact error if not."""
    out = call_llm("Reply with exactly the word: OK", "ping", 300)
    return {
        "ok": bool(out),
        "reply": (out or "")[:50],
        "models_tried_in_order": [LLM_MODEL] + [m for m in LLM_FALLBACK_MODELS if m != LLM_MODEL],
        "last_error": last_llm_error,
    }


GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|salam|assalam[\s-]?o[\s-]?alaikum|good (morning|evening|afternoon)|thanks|thank you)\W*$",
    re.IGNORECASE,
)


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    if GREETING_RE.match(query):
        return ChatResponse(
            reply="Hello! Ask me any question about the Constitution of Pakistan (1973) or the Code of Criminal Procedure (CrPC 1898), and I will answer from those books.",
            reference=None,
            disclaimer=SHORT_DISCLAIMER,
        )

    if collection is None or model is None:
        raise HTTPException(status_code=503, detail="Backend services are starting up.")

    try:
        queries = [query] + expand_query(query)
        print(f"Search queries: {queries}")
        passages = hybrid_retrieve(queries, top_k=7)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ChromaDB query failed: {exc}")

    if not passages or passages[0].get("best_vec", 0.0) < 0.2:
        return ChatResponse(reply=OUT_OF_SCOPE_MSG, reference=None, disclaimer=SHORT_DISCLAIMER)

    result = generate_with_llm(query, passages)
    if result["status"] == "out":
        try:
            wide_passages = hybrid_retrieve(queries, top_k=12, wide=True)
            if wide_passages:
                print("Retrying with wider context before declaring out of scope.")
                result = generate_with_llm(query, wide_passages)
        except Exception as exc:
            print(f"Wide retry failed: {exc}")
    print(f"Answer status={result['status']} reference={result['reference']}")
    return ChatResponse(
        reply=result["reply"],
        reference=result["reference"],
        disclaimer=SHORT_DISCLAIMER,
    )
