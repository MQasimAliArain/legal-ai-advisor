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
SHORT_DISCLAIMER = (
    "Disclaimer: For prototype informational purposes only; not formal legal advice."
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
    """Enforce clean formatting: bold headings and provisions only, no #, >, ---, sub-clause numbers, or trailing citation lists."""
    cleaned = re.sub(r"(?m)^\s*#{1,6}\s*(.+?)\s*$", r"**\1**", text)
    cleaned = re.sub(r"(?m)^\s*>\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", cleaned)
    cleaned = re.sub(r"\b(Article|Section)\s+(\d+[A-Z]?)\(\d+\)", r"\1 \2", cleaned)
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


def hybrid_retrieve(query: str, top_k: int = 6) -> List[dict]:
    """Generic hybrid retrieval (no question-specific hacks) + neighbouring chunks so sections are never cut in half."""
    if collection is None or model is None:
        raise RuntimeError("Retrieval dependencies are not initialized.")

    if collection.count() != len(corpus_docs):
        build_bm25_index()

    q_lower = query.lower()
    query_vec = embed_query(query)
    vec_res = collection.query(
        query_embeddings=[query_vec],
        n_results=30,
        include=["documents", "metadatas", "distances"],
    )

    ids = (vec_res.get("ids") or [[]])[0]
    docs = (vec_res.get("documents") or [[]])[0]
    metas = (vec_res.get("metadatas") or [[]])[0]
    dists = (vec_res.get("distances") or [[]])[0]

    candidates: Dict[str, dict] = {}
    for idx, doc_id in enumerate(ids):
        doc = docs[idx] if idx < len(docs) else ""
        if not doc:
            continue
        meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
        dist = dists[idx] if idx < len(dists) and dists[idx] is not None else 1.0
        vec_sim = max(0.0, 1.0 - float(dist))
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

    bm25_hits = bm25_search(query, top_k=30)
    for doc_id, hit in bm25_hits.items():
        if doc_id in candidates:
            candidates[doc_id]["bm25_norm"] = hit["bm25_norm"]
        else:
            candidates[doc_id] = {
                "id": doc_id,
                "book_title": hit["book_title"],
                "chunk_index": hit["chunk_index"],
                "provisions": hit["provisions"],
                "cleaned": hit["cleaned"],
                "vec_score": 0.25,
                "vec_real": 0.0,
                "bm25_norm": hit["bm25_norm"],
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

    # Take best chunks; a chunk from a different book is only used if it is genuinely close in relevance.
    selected: List[dict] = []
    for item in ranked:
        if len(selected) >= top_k:
            break
        if item["book_title"] != top_book and item["final_score"] < 0.65 * top_score:
            continue
        selected.append(item)

    # Add neighbouring chunks of the 2 best hits so a section and its provisos are complete.
    selected_keys = {(s["book_title"], s["chunk_index"]) for s in selected}
    extras: List[dict] = []
    for item in selected[:2]:
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

    for s in selected:
        s["best_vec"] = best_vec
    final = selected + extras
    final.sort(key=lambda x: (x["book_title"], x["chunk_index"]))
    if final:
        final[0]["best_vec"] = best_vec
    return final


def is_detailed_query(query: str) -> bool:
    q = (query or "").lower()
    detail_triggers = [
        "detail", "details", "detailed", "explain", "elaborate", "comprehensive",
        "list all", "what are all", "all rights", "step by step", "steps",
        "procedure", "in depth", "thorough",
    ]
    return any(trigger in q for trigger in detail_triggers)


def heading_exists(num: str, kind: str, passages: List[dict]) -> bool:
    """True only if this Article/Section number really appears in the retrieved text of the right book."""
    want_const = kind == "constitution"
    pat_heading = re.compile(rf"(?<![\d/.,\-])\b{re.escape(num)}\.\s*[A-Z\"“(]")
    pat_ref = re.compile(rf"\b(?:Article|Section|article|section)s?\s+{re.escape(num)}\b")
    for p in passages:
        is_const = book_kind(p["book_title"]) == "constitution"
        if is_const != want_const:
            continue
        txt = p["cleaned"]
        if pat_heading.search(txt) or pat_ref.search(txt):
            return True
    return False


def extract_citations(reply: str, sources_line: str) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for m in re.finditer(r"\b(Article|Section)\s+(\d{1,3}[A-Z]?)\b", reply):
        kind = "constitution" if m.group(1) == "Article" else "crpc"
        found.append((kind, m.group(2)))
    for m in re.finditer(r"(constitution|crpc|other)\s*:\s*(\d{1,3}[A-Z]?)", sources_line or "", flags=re.IGNORECASE):
        found.append((m.group(1).lower(), m.group(2).upper()))
    seen = set()
    out = []
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
    body = {
        "model": LLM_MODEL,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if "gpt-oss" in LLM_MODEL.lower():
        body["reasoning_effort"] = "low"

    for attempt in range(3):
        try:
            with httpx.Client(timeout=60.0) as client:
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
                print("LLM returned empty content (possibly token limit).")
                return None
            if resp.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2.0 * (attempt + 1))
                continue
            print(f"LLM API error {resp.status_code}: {resp.text}")
            return None
        except Exception as exc:
            print(f"LLM API request failed: {exc}")
            if attempt < 2:
                time.sleep(1.5)
                continue
            return None
    return None


def generate_with_llm(query: str, passages: List[dict]) -> dict:
    """Returns {"status": "ok"|"out"|"error", "reply": str, "reference": Optional[str]}."""
    if not LLM_BASE_URL or not LLM_API_KEY:
        print(f"LLM skipped: LLM_BASE_URL={bool(LLM_BASE_URL)}, LLM_API_KEY={bool(LLM_API_KEY)}")
        return {"status": "error", "reply": BUSY_MSG, "reference": None}

    detailed = is_detailed_query(query)
    max_tokens = 2200 if detailed else 1600

    context_blocks = []
    for idx, p in enumerate(passages, start=1):
        kind = book_kind(p["book_title"])
        label = "Articles" if kind == "constitution" else "Sections"
        context_blocks.append(
            f"[Excerpt {idx} | book_key={kind} | {book_display(kind, p['book_title'])} | numbered provisions here are {label}]\n{p['cleaned']}"
        )
    context_text = "\n\n".join(context_blocks)

    rules = (
        "You are a Pakistani Legal AI Assistant. Always respond strictly in English. "
        "You may use ONLY the numbered excerpts provided, which come from the Constitution of the Islamic Republic of "
        "Pakistan (1973) and the Code of Criminal Procedure (CrPC 1898).\n"
        "1. STRICT GROUNDING: every statement must be directly supported by the excerpts. Never use outside knowledge and "
        "never guess. If the excerpts do not clearly contain the answer (for example the question is about another law such "
        "as the Pakistan Penal Code, contracts, or general knowledge, or the needed provision is not in the excerpts), "
        "output ONLY the exact token: OUT_OF_SCOPE\n"
        "2. CORRECT PROVISIONS: read each numbered provision carefully and attribute to a provision ONLY what its own text "
        "says. Never move the content of one Section/Article onto another number. Cite a Section/Article number ONLY if "
        "its heading (for example '48. Procedure where ...') or a direct reference to it appears in the excerpts. The "
        "Constitution uses Articles; the CrPC uses Sections. Never cite excerpt numbers. Write each provision separately "
        "(for example **Section 47** and **Section 48**, never 'Sections 47 and 48').\n"
        "3. COMPLETENESS: include the conditions, provisos and exceptions that matter for the answer. Do not mention "
        "provisions that are irrelevant to the question.\n"
        "4. CITATION STYLE: no parenthetical citations. Write the provision in **bold** inside the sentence, for example "
        "**Section 48 of the Code of Criminal Procedure (CrPC)** or **Article 10 of the Constitution of Pakistan**. "
        "Never append sub-clause numbers like 'Article 14(2)'.\n"
        "5. FORMAT: ONLY plain text and **bold**. NEVER use '#', blockquotes, '---', italics, or a citations list.\n"
    )
    if detailed:
        rules += (
            "6. STRUCTURE (use exactly these bold headings):\n**Most Relevant**\nThe single most relevant provision in bold "
            "with a clear explanation (3-4 sentences) in simple English.\n**Supported Articles**\nOther relevant provisions in "
            "bold, each with a short explanation of how it relates. If there are none, write: No other directly relevant provision found.\n"
        )
    else:
        rules += (
            "6. LENGTH: short, clear and direct in simple English (3-5 sentences). Start with 'Yes.' or 'No.' (or "
            "'Generally, no.') for yes/no questions ('Can...', 'Does...', 'Is...'), then explain with the exact provision.\n"
        )
    rules += (
        "7. LAST LINE (mandatory when answering): on a new final line write exactly: SOURCES: key:number; key:number "
        "using the book_key of the excerpt and the provision number you relied on, e.g. SOURCES: crpc:48; constitution:10"
    )

    user_prompt = f"Excerpts:\n{context_text}\n\nQuestion: {query}"

    reply_text = ""
    sources_line = ""
    for attempt in range(2):
        content = call_llm(rules, user_prompt, max_tokens)
        if not content:
            return {"status": "error", "reply": BUSY_MSG, "reference": None}
        if content.strip().upper().startswith("OUT_OF_SCOPE") or "OUT_OF_SCOPE" in content[:60]:
            return {"status": "out", "reply": OUT_OF_SCOPE_MSG, "reference": None}

        m = re.search(r"(?im)^\s*\**\s*SOURCES?\s*\**\s*:\s*(.+)$", content)
        sources_line = m.group(1) if m else ""
        body = re.sub(r"(?im)^\s*\**\s*SOURCES?\s*\**\s*:.*$", "", content).strip()
        reply_text = normalize_reply_formatting(body)

        cites = extract_citations(reply_text, "")
        bad = [f"{'Article' if k == 'constitution' else 'Section'} {n}" for k, n in cites if not heading_exists(n, k, passages)]
        if not bad:
            break
        user_prompt = (
            f"Excerpts:\n{context_text}\n\nQuestion: {query}\n\n"
            f"WARNING: your previous answer cited {', '.join(bad)}, which does NOT appear in the excerpts. "
            "Answer again citing only provisions whose number actually appears in the excerpts and describe each "
            "provision only by what its own text says. If the excerpts do not contain the answer, output OUT_OF_SCOPE."
        )

    refs = []
    for kind, num in extract_citations(reply_text, sources_line):
        if heading_exists(num, kind, passages):
            name = book_display(kind, next((p["book_title"] for p in passages if book_kind(p["book_title"]) == kind), "Legal Reference"))
            label = "Article" if kind == "constitution" else "Section"
            refs.append(f"{name} — {label} {num}")
    reference = " | ".join(dict.fromkeys(refs)) if refs else None
    return {"status": "ok", "reply": reply_text, "reference": reference}


@app.get("/health")
def health_check():
    count = collection.count() if collection is not None else 0
    return {
        "status": "ok",
        "collection": COLLECTION_NAME,
        "indexed_chunks": count,
        "llm_enabled": bool(LLM_API_KEY and LLM_BASE_URL),
        "llm_model": LLM_MODEL if (LLM_API_KEY and LLM_BASE_URL) else None,
        "env_file_loaded": ENV_PATH.exists(),
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
        passages = hybrid_retrieve(query, top_k=6)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ChromaDB query failed: {exc}")

    if not passages or passages[0].get("best_vec", 0.0) < 0.2:
        return ChatResponse(reply=OUT_OF_SCOPE_MSG, reference=None, disclaimer=SHORT_DISCLAIMER)

    result = generate_with_llm(query, passages)
    return ChatResponse(
        reply=result["reply"],
        reference=result["reference"],
        disclaimer=SHORT_DISCLAIMER,
    )
