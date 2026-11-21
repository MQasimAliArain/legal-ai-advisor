import math
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

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
    "Disclaimer: This is for General Guidance only not a Professional Legal advice."
)

OUT_OF_SCOPE_MSG = (
    "This question is outside the scope of my indexed legal corpus or is not clearly answered in the provided excerpts. "
    "My current knowledge base only includes the Constitution of the Islamic Republic of Pakistan (1973) and the Code of Criminal Procedure (CrPC 1898)—other laws (such as the Pakistan Penal Code or civil statutes) are not indexed here."
)

STOP_WORDS = {
    "what", "is", "the", "a", "an", "of", "in", "on", "for", "to", "and",
    "or", "how", "when", "where", "why", "who", "can", "should", "does",
    "do", "are", "was", "were", "be", "been", "with", "from", "by", "under",
    "this", "that", "these", "those", "it", "its", "as", "at", "into",
    "someone", "person", "they", "them", "their", "even", "only", "also",
    "would", "could", "may", "might", "must", "shall", "any", "all", "during",
}

# Broad legal & constitutional synonym expansion so everyday wording matches statutory terms
LEGAL_SYNONYMS = {
    "movement": "freedom of movement enter and move freely throughout pakistan public interest",
    "travel": "freedom of movement enter and move freely throughout pakistan",
    "emergency": "proclamation of emergency fundamental rights suspended public interest",
    "public": "public interest public order public safety reasonable restrictions",
    "government": "state federal government provincial government law authority",
    "restrict": "reasonable restrictions imposed by law subject to any reasonable restrictions",
    "restriction": "reasonable restrictions imposed by law subject to any reasonable restrictions",
    "apartment": "house place zenana apartment",
    "house": "house place dwelling apartment",
    "home": "house place dwelling apartment",
    "woman": "woman female zenana modesty decency",
    "female": "woman female zenana modesty decency",
    "withdraw": "withdraw notice facility zenana",
    "privacy": "privacy zenana apartment dignity home",
    "search": "search searched searching articles found",
    "body": "person body searched articles found",
    "pocket": "articles found upon him searched",
    "money": "articles found upon him safe custody",
    "phone": "articles found upon him safe custody",
    "clothes": "wearing apparel necessary",
    "convicted": "convicted conviction bail arrested",
    "arrest": "arrest arrested custody warrant",
    "police": "police officer magistrate",
    "bail": "bail bailable non-bailable bond",
    "fir": "information cognizable offence officer in charge",
    "confess": "confession witness against himself compelled accused offence",
    "confession": "confession magistrate statement witness against himself compelled",
    "force": "compelled torture force coercion accused witness against himself",
    "forced": "compelled torture force coercion accused witness against himself",
    "evidence": "evidence confession witness against himself torture",
    "accused": "accused person charged offence witness against himself",
    "charged": "charged offence accused person trial",
    "offence": "offence punishable by law act omitted",
    "punished": "punished punishment retrospective offence law greater penalty",
    "punishment": "punishment retrospective offence greater penalty",
    "retrospective": "retrospective punishment act punishable at the time offence greater penalty",
    "retroactive": "retrospective punishment act punishable at the time offence greater penalty",
    "past": "retrospective punishment act punishable at the time offence",
    "ago": "retrospective punishment act punishable at the time offence",
    "torture": "torture dignity extracting evidence",
    "twice": "same offence more than once acquitted convicted",
    "speech": "freedom of speech and expression restrictions",
    "criticize": "freedom of speech and expression public order",
    "language": "language script culture preserve promote",
    "culture": "language script culture preserve promote",
    "religion": "religion religious instruction ceremony worship profess practice",
    "religious": "religion religious instruction ceremony worship profess practice",
    "institution": "educational institution receiving aid",
    "school": "educational institution receiving aid",
    "property": "property acquire hold dispose",
    "equality": "equality equal protection citizens",
    "life": "life liberty security person",
    "detention": "arrest detention safeguards twenty-four hours",
    "lawyer": "legal practitioner counsel defence",
    "judge": "magistrate court judge session",
    "witness": "witness examination summons",
    "warrant": "warrant arrest search summons",
    "assembly": "freedom of assembly peaceful without arms",
    "association": "freedom of association unions",
    "trade": "freedom of trade business or profession",
    "remand": "remand custody magistrate detention",
    "trial": "trial court inquiry magistrate charge",
    "appeal": "appeal court conviction sentence",
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


def extract_reference_from_reply(reply_text: str, passages: List[dict]) -> Optional[str]:
    """Match the primary Article/Section cited in the generated reply to its book title."""
    bold_matches = re.findall(r"\*\*((?:Article|Section)\s+\d+[A-Z]?[^*\n]*?)\*\*", reply_text or "")
    for raw_match in bold_matches:
        prov_match = re.search(r"\b(Article|Section)\s+(\d+[A-Z]?)\b", raw_match, flags=re.IGNORECASE)
        if not prov_match:
            continue
        kind = prov_match.group(1).capitalize()
        num = prov_match.group(2).upper()
        match_lower = raw_match.lower()

        if "criminal" in match_lower or "crpc" in match_lower or kind == "Section":
            matched_book = next(
                (
                    str(p.get("book_title")).strip()
                    for p in passages
                    if p.get("book_title")
                    and ("criminal" in str(p.get("book_title")).lower() or "crpc" in str(p.get("book_title")).lower())
                ),
                "Code of Criminal Procedure, 1898",
            )
            return f"{matched_book} - Section {num}"

        matched_book = next(
            (
                str(p.get("book_title")).strip()
                for p in passages
                if p.get("book_title") and "constitution" in str(p.get("book_title")).lower()
            ),
            "Constitution of Islamic Republic of Pakistan, 1973",
        )
        return f"{matched_book} - Article {num}"

    for p in passages:
        book = str(p.get("book_title") or "Legal Reference").strip()
        prov = str(p.get("provisions") or "").strip()
        if prov:
            first_prov = prov.split(",")[0].strip()
            label = "Section" if "criminal" in book.lower() or "crpc" in book.lower() else "Article"
            return f"{book} - {label} {first_prov}"

    return str(passages[0].get("book_title") or "Legal Reference").strip() if passages else None


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if len(t) >= 2 and t not in STOP_WORDS]


def split_into_fine_provisions(cleaned_text: str) -> List[str]:
    """Split multi-section chunks into individual numbered Articles/Sections so single provisions don't get buried."""
    parts = re.split(r"(?=\b\d{1,3}[A-Z]?\.\s+[A-Z])", cleaned_text)
    fine = [p.strip() for p in parts if len(p.strip()) >= 40]
    return fine if len(fine) > 1 else [cleaned_text]


def build_bm25_index():
    """Load all chunks from ChromaDB and also index fine-grained individual Articles/Sections for sharp BM25 recall."""
    global corpus_docs, idf_scores, avg_doc_len
    if collection is None:
        return

    all_data = collection.get(include=["documents", "metadatas"])
    ids = all_data.get("ids") or []
    docs = all_data.get("documents") or []
    metas = all_data.get("metadatas") or []

    corpus_docs = []
    df_counter: Counter = Counter()
    total_len = 0

    for i, doc_id in enumerate(ids):
        raw_doc = docs[i] if i < len(docs) else ""
        if not raw_doc:
            continue
        meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
        cleaned = clean_text(raw_doc)
        book_title = meta.get("book_title", "Legal Reference")
        chunk_index = meta.get("chunk_index", 0)
        provisions = meta.get("provisions", "")

        sub_units = split_into_fine_provisions(cleaned)
        entries = [(doc_id, cleaned, provisions)]
        if len(sub_units) > 1:
            for sub_idx, sub_text in enumerate(sub_units):
                m = re.match(r"^(\d{1,3}[A-Z]?)\.\s+", sub_text)
                sub_prov = m.group(1) if m else provisions
                entries.append((f"{doc_id}__sub_{sub_idx}", sub_text, sub_prov))

        for entry_id, entry_text, entry_prov in entries:
            toks = tokenize(entry_text)
            if not toks:
                continue
            tf = Counter(toks)
            total_len += len(toks)
            for term in tf.keys():
                df_counter[term] += 1

            corpus_docs.append({
                "id": entry_id,
                "parent_id": doc_id,
                "book_title": book_title,
                "chunk_index": chunk_index,
                "provisions": entry_prov,
                "cleaned": entry_text,
                "tf": tf,
                "doc_len": len(toks),
            })

    n_docs = max(len(corpus_docs), 1)
    avg_doc_len = max(total_len / n_docs, 1.0)
    idf_scores = {
        term: math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        for term, df in df_counter.items()
    }
    print(
        f"Loaded {len(corpus_docs)} fine-grained units from {len(ids)} Chroma chunks into Hybrid BM25+Vector index. "
        f"LLM enabled: {bool(LLM_API_KEY and LLM_BASE_URL)} ({LLM_MODEL})"
    )


@app.on_event("startup")
def startup_event():
    global model, collection
    model = SentenceTransformer(EMBED_MODEL_NAME)
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"Collection load error: {e}")
        collection = None
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


def expand_legal_query(query: str) -> str:
    """General synonym expansion from everyday English to statutory terminology."""
    tokens = tokenize(query)
    expansions = []
    for tok in tokens:
        if tok in LEGAL_SYNONYMS:
            expansions.append(LEGAL_SYNONYMS[tok])
    if expansions:
        return f"{query} {' '.join(expansions)}"
    return query


def bm25_search(query: str, top_k: int = 60) -> Dict[str, dict]:
    q_tokens = tokenize(query)
    if not q_tokens or not corpus_docs:
        return {}

    raw_tokens = tokenize(query.split("?")[0])
    bigrams = [" ".join(raw_tokens[i:i + 2]) for i in range(len(raw_tokens) - 1)]
    trigrams = [" ".join(raw_tokens[i:i + 3]) for i in range(len(raw_tokens) - 2)]

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
    max_s = scored[0][0] if scored else 1.0

    results = {}
    for s, doc in scored[:top_k]:
        results[doc["id"]] = {
            **doc,
            "bm25_norm": s / max_s,
        }
    return results


def hybrid_retrieve(query: str, top_k: int = 16) -> List[dict]:
    if not corpus_docs and collection is not None:
        build_bm25_index()

    q_lower = query.lower()
    expanded_query = expand_legal_query(query)

    vec_res_raw = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=50,
        include=["documents", "metadatas", "distances"],
    )
    vec_res_exp = collection.query(
        query_embeddings=[embed_query(expanded_query)],
        n_results=50,
        include=["documents", "metadatas", "distances"],
    )

    candidates: Dict[str, dict] = {}
    for vec_res, weight in [(vec_res_raw, 1.0), (vec_res_exp, 0.95)]:
        ids = (vec_res.get("ids") or [[]])[0]
        docs = (vec_res.get("documents") or [[]])[0]
        metas = (vec_res.get("metadatas") or [[]])[0]
        dists = (vec_res.get("distances") or [[]])[0]

        for idx, doc_id in enumerate(ids):
            doc = docs[idx] if idx < len(docs) else ""
            if not doc:
                continue
            meta = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
            dist = dists[idx] if idx < len(dists) and dists[idx] is not None else 1.0
            vec_sim = max(0.0, 1.0 - float(dist)) * weight

            if doc_id not in candidates or vec_sim > candidates[doc_id]["vec_score"]:
                candidates[doc_id] = {
                    "id": doc_id,
                    "parent_id": doc_id,
                    "book_title": meta.get("book_title", "Legal Reference"),
                    "chunk_index": meta.get("chunk_index", 0),
                    "provisions": meta.get("provisions", ""),
                    "cleaned": clean_text(doc),
                    "vec_score": vec_sim,
                    "bm25_norm": 0.0,
                }

    bm25_hits = bm25_search(expanded_query, top_k=65)
    for doc_id, hit in bm25_hits.items():
        parent_id = hit.get("parent_id", doc_id)
        parent_vec = candidates[parent_id]["vec_score"] if parent_id in candidates else 0.45
        if doc_id in candidates:
            candidates[doc_id]["bm25_norm"] = hit["bm25_norm"]
        else:
            candidates[doc_id] = {
                "id": doc_id,
                "parent_id": parent_id,
                "book_title": hit["book_title"],
                "chunk_index": hit["chunk_index"],
                "provisions": hit["provisions"],
                "cleaned": hit["cleaned"],
                "vec_score": parent_vec,
                "bm25_norm": hit["bm25_norm"],
            }

    ranked = []
    for item in candidates.values():
        combined = 0.45 * item["vec_score"] + 0.55 * item["bm25_norm"]
        lower = item["cleaned"].lower()

        if "__sub_" in item["id"] and item["bm25_norm"] > 0.25:
            combined += 0.12

        if (
            "preamble" not in q_lower
            and "objectives resolution" not in q_lower
            and ("now, therefore, we, the people of pakistan" in lower or "delegated to the state of pakistan" in lower)
        ):
            combined -= 0.30

        item["final_score"] = combined
        ranked.append(item)

    ranked.sort(key=lambda x: x["final_score"], reverse=True)

    selected: List[dict] = []
    seen_texts = set()
    books_seen = []
    for item in ranked:
        if item["book_title"] not in books_seen:
            books_seen.append(item["book_title"])

    for book_name in books_seen[:2]:
        added_for_book = 0
        for item in ranked:
            sig = item["cleaned"][:120]
            if item["book_title"] == book_name and sig not in seen_texts:
                selected.append(item)
                seen_texts.add(sig)
                added_for_book += 1
                if added_for_book >= 6:
                    break

    for item in ranked:
        if len(selected) >= top_k:
            break
        sig = item["cleaned"][:120]
        if sig not in seen_texts:
            selected.append(item)
            seen_texts.add(sig)

    selected.sort(key=lambda x: x["final_score"], reverse=True)
    return selected


def is_detailed_query(query: str) -> bool:
    q = (query or "").lower()
    detail_triggers = [
        "detail", "details", "detailed", "explain", "elaborate", "comprehensive",
        "list all", "what are all", "all rights", "step by step", "steps",
        "procedure", "in depth", "thorough",
    ]
    return any(trigger in q for trigger in detail_triggers)


def generate_with_llm(query: str, passages: List[dict]) -> Optional[str]:
    if not LLM_BASE_URL or not LLM_API_KEY:
        print(f"LLM skipped: LLM_BASE_URL={bool(LLM_BASE_URL)}, LLM_API_KEY={bool(LLM_API_KEY)}")
        return None

    detailed = is_detailed_query(query)
    max_tokens = 750 if detailed else 480

    context_blocks = []
    for idx, p in enumerate(passages, start=1):
        prov_label = f" | Provisions in chunk: {p['provisions']}" if p.get("provisions") else ""
        context_blocks.append(
            f"[Source {idx}: {p['book_title']}.pdf — Part {int(p['chunk_index']) + 1}{prov_label}]\n{p['cleaned']}"
        )
    context_text = "\n\n".join(context_blocks)

    scope_rule = (
        "STRICT GROUNDING & OUT-OF-SCOPE RULE: Your corpus ONLY contains the Constitution of Pakistan (1973) and "
        "the Code of Criminal Procedure (CrPC 1898). Carefully inspect ALL provided excerpts. Whenever ANY excerpt "
        "contains an Article or Section that relates to the user's question (including fundamental rights, protection "
        "against retrospective punishment, protection against self-incrimination/confessions/torture, freedom of movement, "
        "emergency/proclamation provisions, reasonable restrictions, religious instruction/institutions, arrest/search/bail/FIR/procedure, "
        "or constitutional principles), you MUST answer clearly and accurately using the provided excerpts and your legal "
        "knowledge of the Constitution of Pakistan (1973) and CrPC (1898) without outputting OUT_OF_SCOPE. "
        "Output ONLY the exact token OUT_OF_SCOPE only when the question asks about a completely different statute or "
        "subject outside the Constitution of Pakistan (1973) and CrPC (1898) (such as specific PPC offence penalties, "
        "family/divorce/inheritance statutes, tax, labour, or corporate law) AND no provided excerpt covers it."
    )

    citation_rule = (
        "BOLD ONLY RULE: Do NOT use parenthetical citations like '(Article 15 of the Constitution of Pakistan)'. "
        "Make every Article or Section and its book/statute **bold** directly in the text—for example, "
        "**Article 15 of the Constitution of Pakistan** or **Section 48 of the Code of Criminal Procedure (CrPC)**. "
        "NEVER refer to a chunk/part number as an Article or Section, and NEVER append sub-clause numbers like 'Article 14(2)'."
    )

    formatting_rule = (
        "CLEAN FORMATTING RULE: Use ONLY plain text and **bold** formatting. NEVER use '#', '##', '###', blockquotes "
        "('>' or quotes), '---' dividers, italics, or a separate 'Citations' list at the bottom."
    )

    style_and_length_rule = (
        "DETAILED MODE RULE: Keep it clear and concise—not a long essay. Follow this exact structure using ONLY "
        "these **Bold Headings**:\n"
        "**Most Relevant**\n"
        "State the single most relevant **Article** or **Section** and its book in **bold**, followed by a short "
        "explanation (2–3 sentences) of that main provision in simple, everyday English.\n"
        "**Supported Articles**\n"
        "List the other relevant **Articles** and **Sections** across the books in **bold**, followed by a short "
        "explanation (2–3 sentences) of how those supported provisions relate to the question in simple, everyday English."
        if detailed
        else "CONCISE MODE RULE: Keep the answer short, clear, and direct in simple everyday English (2–3 sentences "
        "total). Include the **bold** Article or Section from ALL applicable books if more than one book has relevant "
        "provisions. Start with 'Yes.' or 'No.' (or 'Generally, no.') when answering a yes/no question ('Can...', "
        "'Does...', 'Is...')."
    )

    system_prompt = (
        "You are a Pakistani Legal AI Assistant. Always respond strictly in English. Answer using the "
        "provided excerpts from the Constitution of the Islamic Republic of Pakistan (1973) and the Code of "
        "Criminal Procedure (1898). "
        f"{scope_rule} {citation_rule} {formatting_rule} {style_and_length_rule}"
    )

    for attempt in range(2):
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(
                    f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {LLM_API_KEY}",
                    },
                    json={
                        "model": LLM_MODEL,
                        "temperature": 0.1,
                        "max_tokens": max_tokens,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user",
                                "content": f"Context:\n{context_text}\n\nQuestion: {query}",
                            },
                        ],
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                    if content:
                        return normalize_reply_formatting(content)
                elif resp.status_code == 429 and attempt == 0:
                    time.sleep(1.5)
                    continue
                else:
                    print(f"Groq API error {resp.status_code}: {resp.text}")
                    break
        except Exception as exc:
            print(f"Groq API request failed: {exc}")
            break

    return None


@app.get("/health")
def health_check():
    count = collection.count() if collection is not None else 0
    return {
        "status": "ok",
        "collection": COLLECTION_NAME,
        "indexed_chunks": count,
        "fine_index_units": len(corpus_docs),
        "llm_enabled": bool(LLM_API_KEY and LLM_BASE_URL),
        "llm_model": LLM_MODEL if (LLM_API_KEY and LLM_BASE_URL) else None,
        "env_file_loaded": ENV_PATH.exists(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    if collection is None or model is None:
        raise HTTPException(status_code=503, detail="Backend services are starting up.")

    try:
        top_passages = hybrid_retrieve(query, top_k=16)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ChromaDB query failed: {exc}")

    if not top_passages:
        return ChatResponse(
            reply=OUT_OF_SCOPE_MSG,
            reference=None,
            disclaimer=SHORT_DISCLAIMER,
        )

    llm_reply = generate_with_llm(query, top_passages)
    if llm_reply and llm_reply.strip().upper() == "OUT_OF_SCOPE":
        return ChatResponse(
            reply=OUT_OF_SCOPE_MSG,
            reference=None,
            disclaimer=SHORT_DISCLAIMER,
        )

    if llm_reply:
        reply_text = llm_reply
    else:
        return ChatResponse(
            reply=OUT_OF_SCOPE_MSG,
            reference=None,
            disclaimer=SHORT_DISCLAIMER,
        )

    single_reference = extract_reference_from_reply(reply_text, top_passages)

    return ChatResponse(
        reply=reply_text,
        reference=single_reference,
        disclaimer=SHORT_DISCLAIMER,
    )