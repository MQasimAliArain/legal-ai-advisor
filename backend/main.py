import math
import os
import re
import threading
import time
from collections import Counter, OrderedDict
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


def _csv(value: Optional[str]) -> List[str]:
    return [m.strip() for m in (value or "").split(",") if m.strip()]


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------
# Provider 1: Groq (or any OpenAI-compatible endpoint set through LLM_BASE_URL)
LLM_API_KEY = (os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or ("https://api.groq.com/openai/v1" if LLM_API_KEY else "")
).strip()
LLM_MODEL = (os.getenv("LLM_MODEL") or "openai/gpt-oss-120b").strip()
LLM_FALLBACK_MODELS = _csv(os.getenv("LLM_FALLBACK_MODELS") or "llama-3.3-70b-versatile,openai/gpt-oss-20b")
# Extra Groq models are ALWAYS appended (even if Railway still has old env values) because
# every Groq model has its own separate free quota.
LLM_EXTRA_MODELS = _csv(os.getenv("LLM_EXTRA_MODELS") or "meta-llama/llama-4-scout-17b-16e-instruct")
# Small/cheap models used for the short "translate + rewrite search query" step to save quota.
LLM_LIGHT_MODELS = _csv(os.getenv("LLM_LIGHT_MODELS") or "llama-3.1-8b-instant,openai/gpt-oss-20b")

# Provider 2: Google Gemini (free tier, much larger token limits than Groq free)
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
GEMINI_BASE_URL = (
    os.getenv("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta/openai"
).strip()
GEMINI_MODELS = _csv(os.getenv("GEMINI_MODELS") or "gemini-2.5-flash,gemini-2.5-flash-lite")
GEMINI_LIGHT_MODELS = _csv(os.getenv("GEMINI_LIGHT_MODELS") or "gemini-2.5-flash-lite")
# "gemini_first" (default, only matters when both keys are set) or "groq_first"
LLM_PRIORITY = (os.getenv("LLM_PRIORITY") or "gemini_first").strip().lower()

LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "45"))
LLM_MAX_WAIT_SECONDS = float(os.getenv("LLM_MAX_WAIT_SECONDS", "8"))

last_llm_error: str = ""
model_cooldown: Dict[str, float] = {}  # "provider:model" -> unix time until which the model is skipped

# ---------------------------------------------------------------------------
# Messages (English / Urdu / Roman Urdu)
# ---------------------------------------------------------------------------
SHORT_DISCLAIMER = (
    "Disclaimer: This is only for general guidance, not a professional legal support. "
   
)

OUT_OF_SCOPE_MSG = (
    "This question is outside the scope of my indexed legal corpus or is not clearly answered in the provided excerpts. "
    "My current knowledge base only includes the Constitution of the Islamic Republic of Pakistan (1973) and the Code of Criminal Procedure (CrPC 1898)—other laws (such as the Pakistan Penal Code or civil statutes) are not indexed here."
)

CONST_NAME = "Constitution of the Islamic Republic of Pakistan, 1973"
CRPC_NAME = "Code of Criminal Procedure (CrPC), 1898"

LANGS: Dict[str, dict] = {
    "english": {
        "simple_name": "English",
        "instruction": "Always respond strictly in English.",
        "disclaimer": SHORT_DISCLAIMER,
        "out_of_scope": OUT_OF_SCOPE_MSG,
        "greeting": (
            "Hello! Ask me any question about the Constitution of Pakistan (1973) or the Code of Criminal "
            "Procedure (CrPC 1898), and I will answer from those books."
        ),
        "fallback_intro": "Here are the most relevant passages I found in the indexed law for your question:",
        "most_relevant": "Most Relevant",
        "supported": "Supported Articles",
        "no_other": "No other directly relevant provision found.",
        "yes": "Yes.",
        "no": "No.",
        "generally_no": "Generally, no.",
        # names / labels used for references and citations
        "const_name": CONST_NAME,
        "crpc_name": CRPC_NAME,
        "law_short_const": "Constitution of Pakistan",
        "law_short_crpc": "Code of Criminal Procedure (CrPC)",
        "article_label": "Article",
        "section_label": "Section",
        "of_article": "of",
        "of_section": "of",
    },
    "urdu": {
        "simple_name": "Urdu",
        "instruction": (
            "The user wrote in Urdu. Write your ENTIRE answer in clear, simple Urdu using Urdu script only "
            "(do not use Roman/Latin letters for Urdu words). The only exception: write every legal citation EXACTLY "
            "in this English template, with nothing added or translated around it, because the system verifies it and then "
            "converts it to Urdu automatically: **Section 48 of the Code of Criminal Procedure (CrPC)** or "
            "**Article 12 of the Constitution of Pakistan** (Latin digits). Never write the words 'دفعہ' or 'آرٹیکل' "
            "yourself. The excerpts are in English: understand them and explain their meaning in Urdu."
        ),
        "disclaimer": (
            "دستبرداری:یہ صرف عمومی رہنمائی ہے، پیشہ ورانہ قانونی معاونت نہیں۔ "
     
        ),
        "out_of_scope": (
            "یہ سوال میرے انڈیکس شدہ قانونی مواد کے دائرہ کار سے باہر ہے یا فراہم کردہ اقتباسات میں اس کا واضح جواب موجود نہیں۔ "
            "میرے موجودہ علمی ذخیرے میں صرف اسلامی جمہوریہ پاکستان کا آئین (1973) اور مجموعہ ضابطہ فوجداری "
            "(CrPC 1898) شامل ہیں۔ دیگر قوانین (مثلاً مجموعہ تعزیراتِ پاکستان یا دیوانی قوانین) یہاں انڈیکس نہیں کیے گئے۔"
        ),
        "greeting": (
            "السلام علیکم! آپ مجھ سے پاکستان کے آئین (1973) یا مجموعہ ضابطہ فوجداری (CrPC 1898) کے بارے میں "
            "کوئی بھی سوال پوچھ سکتے ہیں، میں انہی کتابوں سے جواب دوں گا۔"
        ),
        "fallback_intro": (
            "آپ کے سوال سے سب سے زیادہ متعلقہ اقتباسات، جو انڈیکس شدہ قانون میں ملے، درج ذیل ہیں (اصل متن انگریزی میں ہے):"
        ),
        "most_relevant": "سب سے متعلقہ",
        "supported": "دیگر متعلقہ احکامات",
        "no_other": "کوئی اور براہِ راست متعلقہ حکم نہیں ملا۔",
        "yes": "جی ہاں۔",
        "no": "نہیں۔",
        "generally_no": "عمومی طور پر نہیں۔",
        "const_name": "آئینِ اسلامی جمہوریہ پاکستان، 1973",
        "crpc_name": "مجموعہ ضابطہ فوجداری (CrPC)، 1898",
        "law_short_const": "آئینِ پاکستان",
        "law_short_crpc": "مجموعہ ضابطہ فوجداری (CrPC)",
        "article_label": "آرٹیکل",
        "section_label": "دفعہ",
        "of_article": "کا",
        "of_section": "کی",
    },
    "roman_urdu": {
        "simple_name": "Roman Urdu",
        "instruction": (
            "The user wrote in Roman Urdu (Urdu written in English/Latin letters, the way Pakistanis text, for example "
            "'Yeh dafa kehti hai ke ...'). Write your ENTIRE answer in simple Roman Urdu using Latin letters only "
            "(do not use Urdu/Arabic script). The only exception: write every legal citation EXACTLY in this English "
            "template, with nothing added or translated around it, because the system verifies it and then converts it to "
            "Roman Urdu automatically: **Section 48 of the Code of Criminal Procedure (CrPC)** or "
            "**Article 12 of the Constitution of Pakistan**. Never write the word 'Dafa' yourself. "
            "The excerpts are in English: understand them and explain their meaning in Roman Urdu."
        ),
        "disclaimer": (
            "Disclaimer: Yeh sirf umoomi rehnumai hai, peshawarana qanooni madad nahi."
        ),
        "out_of_scope": (
            "Yeh sawal mere indexed qanooni zakhire ke dayre se bahar hai ya faraham kiye gaye iqtebasaat mein iska wazeh jawab mojood nahi. "
            "Mera mojooda knowledge base sirf Islami Jamhuriya Pakistan ka Aaeen (1973) aur Code of Criminal Procedure (CrPC 1898) "
            "par mushtamil hai. Dusre qawaneen (jaise Pakistan Penal Code ya diwani qawaneen) yahan index nahi kiye gaye."
        ),
        "greeting": (
            "Assalam o Alaikum! Aap mujh se Pakistan ke Aaeen (1973) ya Code of Criminal Procedure (CrPC 1898) ke bare mein "
            "koi bhi sawal pooch sakte hain, main inhi kitabon se jawab doon ga."
        ),
        "fallback_intro": (
            "Aap ke sawal se sab se zyada mutaliqa iqtebasaat jo indexed qanoon mein milay, yeh hain (asal matn English mein hai):"
        ),
        "most_relevant": "Sab Se Mutaliqa",
        "supported": "Dusre Mutaliqa Ahkamat",
        "no_other": "Koi aur seedha mutaliqa hukm nahi mila.",
        "yes": "Ji haan.",
        "no": "Nahi.",
        "generally_no": "Aam tor par nahi.",
        "const_name": "Aaeen-e-Islami Jamhuriya Pakistan, 1973",
        "crpc_name": "Majmua Zabta Faujdari (CrPC), 1898",
        "law_short_const": "Aaeen-e-Pakistan",
        "law_short_crpc": "Majmua Zabta Faujdari (CrPC)",
        "article_label": "Article",
        "section_label": "Dafa",
        "of_article": "ka",
        "of_section": "ki",
    },
}

STOP_WORDS = {
    "what", "is", "the", "a", "an", "of", "in", "on", "for", "to", "and",
    "or", "how", "when", "where", "why", "who", "can", "should", "does",
    "do", "are", "was", "were", "be", "been", "with", "from", "by", "under",
    "this", "that", "these", "those", "it", "its", "as", "at", "into",
    "someone", "person", "they", "them", "their",
}

# ---------------------------------------------------------------------------
# Language detection (English / Urdu / Roman Urdu)
# ---------------------------------------------------------------------------
URDU_CHAR_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# Common Roman Urdu words that are NOT normal English words.
ROMAN_URDU_WORDS = {
    "kya", "hai", "hain", "hoon", "hun", "tha", "thi", "the_", "hoga", "hogi", "honge", "hota", "hoti", "hote",
    "ka", "ki", "ke", "ko", "se", "mein", "mei", "pe", "par_", "ne", "kar", "kare", "karna", "karne", "karni",
    "kr", "krna", "kiya", "kia", "kiye", "diya", "liya", "gaya", "gayi", "gaye", "raha", "rahi", "rahe",
    "nahi", "nahin", "nai", "koi", "kisi", "kuch", "sab", "aur", "agar", "lekin", "magar", "bhi", "sirf",
    "mujhe", "mera", "meri", "mere", "hum", "humein", "hamen", "mujh", "tum", "aap", "woh", "wo", "yeh", "ye",
    "uska", "uski", "uske", "unka", "unki", "unke", "iska", "iski", "iske", "apna", "apni", "apne",
    "kaise", "kese", "kab", "kahan", "kyun", "kyu", "kon", "kaun", "kitna", "kitni", "kitne",
    "sakta", "sakti", "sakte", "chahiye", "chahie", "milta", "milti", "milte", "wala", "wali", "wale",
    "liye", "lye", "jab", "tab", "jo", "batao", "batain", "bataiye", "btao", "bataen", "samjhao",
    "shukriya", "shukria", "jawab", "sawal", "mushkil", "madad", "kisko", "kiska", "kiski",
}

GLOSSARY = {
    "giraftar": "arrest", "giraftari": "arrest", "girftar": "arrest", "girftari": "arrest",
    "گرفتار": "arrest", "گرفتاری": "arrest",
    "pulis": "police", "پولیس": "police",
    "zamanat": "bail", "zamant": "bail", "ضمانت": "bail",
    "adalat": "court", "عدالت": "court",
    "muqadma": "case trial", "mukadma": "case trial", "muqadmay": "case trial", "مقدمہ": "case trial",
    "hirasat": "custody", "حراست": "custody",
    "qaidi": "prisoner", "قیدی": "prisoner",
    "jel": "jail", "جیل": "jail",
    "tashadud": "torture", "تشدد": "torture",
    "talashi": "search", "تلاشی": "search", "chapa": "search raid", "چھاپہ": "search raid",
    "aurat": "woman", "aurtain": "women", "khatoon": "woman", "khawateen": "women",
    "عورت": "woman", "عورتیں": "women", "خاتون": "woman",
    "huquq": "rights", "haq": "right", "حقوق": "rights", "حق": "right",
    "azadi": "freedom liberty", "آزادی": "freedom liberty",
    "mazhab": "religion", "مذہب": "religion",
    "wakeel": "lawyer legal practitioner", "وکیل": "lawyer legal practitioner",
    "gawah": "witness", "gawahi": "evidence witness", "گواہ": "witness", "گواہی": "evidence witness",
    "saza": "punishment", "sazaa": "punishment", "سزا": "punishment",
    "ilzam": "accused accusation", "الزام": "accused accusation",
    "mulzim": "accused", "ملزم": "accused",
    "mujrim": "offender convict", "مجرم": "offender convict",
    "jurm": "offence", "جرم": "offence",
    "iqrar": "confession", "اقرار": "confession",
    "qanoon": "law", "kanoon": "law", "qanun": "law", "قانون": "law",
    "aaeen": "constitution", "aain": "constitution", "ayeen": "constitution", "aeen": "constitution",
    "آئین": "constitution", "دستور": "constitution",
    "shehri": "citizen", "شہری": "citizen",
    "jaidad": "property", "جائیداد": "property",
    "tafteesh": "investigation", "tehqiqat": "investigation", "تفتیش": "investigation", "تحقیقات": "investigation",
    "shikayat": "complaint", "شکایت": "complaint",
    "insaf": "justice", "انصاف": "justice",
    "izzat": "dignity", "عزت": "dignity",
    "ghulami": "slavery", "غلامی": "slavery",
    "bacha": "child", "bachay": "children", "bachon": "children", "بچہ": "child", "بچے": "children",
    "hukumat": "government", "حکومت": "government",
    "sadar": "president", "صدر": "president",
    "wazir": "minister", "وزیر": "minister",
    "intikhab": "election", "intikhabat": "election", "انتخابات": "election",
    "izhar": "expression speech", "اظہار": "expression speech",
    "bagair": "without", "bina": "without", "بغیر": "without",
    "ghantay": "hours", "ghante": "hours", "گھنٹے": "hours",
}

_ROMAN_DETECT_WORDS = {w for w in ROMAN_URDU_WORDS if not w.endswith("_")} | {k for k in GLOSSARY if k.isascii()}


def detect_language(text: str) -> str:
    """Returns 'urdu' (Arabic script), 'roman_urdu' (Urdu in Latin letters) or 'english'."""
    text = text or ""
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return "english"
    if len(URDU_CHAR_RE.findall(text)) / len(letters) >= 0.3:
        return "urdu"
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return "english"
    hits = sum(1 for w in words if w in _ROMAN_DETECT_WORDS)
    if hits >= 2 or (hits >= 1 and hits / len(words) >= 0.34):
        return "roman_urdu"
    return "english"


def glossary_translate(text: str) -> str:
    """Offline last-resort translation of key legal words, used only when no LLM is reachable."""
    out: List[str] = []
    for tok in re.findall(r"[\w']+", (text or "").lower()):
        if tok in GLOSSARY:
            out.append(GLOSSARY[tok])
        elif tok.isdigit():
            out.append(tok)
        elif tok.isascii() and len(tok) >= 3 and tok not in _ROMAN_DETECT_WORDS:
            out.append(tok)
    result = " ".join(out).strip()
    return result or text


# ---------------------------------------------------------------------------
# Citation localization (English template -> Urdu / Roman Urdu)
# ---------------------------------------------------------------------------
_EASTERN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUM = r"\d{1,3}[A-Z]?(?:\([A-Za-z0-9]+\))*"
_CONST_PAT = r"Constitution(?:\s+of\s+(?:the\s+Islamic\s+Republic\s+of\s+)?Pakistan)?(?:\s*,?\s*1973)?"
_CRPC_PAT = r"(?:Code\s+of\s+Criminal\s+Procedure(?:\s*\(\s*CrPC\s*\))?|CrPC)(?:\s*,?\s*1898)?"
_FULL_CITE_RE = re.compile(
    rf"(?P<b1>\*\*)?\b(?P<label>Article|Section)\s+(?P<num>{_NUM})(?P<b2>\*\*)?\s+of\s+the\s+"
    rf"(?:(?P<const>{_CONST_PAT})|(?P<crpc>{_CRPC_PAT}))(?P<b3>\*\*)?",
    re.IGNORECASE,
)
_BARE_CITE_RE = re.compile(rf"\b(Article|Section)\s+({_NUM})", re.IGNORECASE)
_NATIVE_CITE_RE = re.compile(
    r"(آرٹیکلز|آرٹیکل|دفعات|دفعہ|Dafaat|Dafaa|Dafat|Dafa)\s*([0-9۰-۹٠-٩]{1,3}[A-Z]?(?:\([A-Za-z0-9]+\))*)",
    re.IGNORECASE,
)


def to_english_labels(text: str) -> str:
    """If the model wrote 'دفعہ 48' / 'Dafa 48' / 'آرٹیکل 12' itself, turn it back into 'Section 48' / 'Article 12'
    so the provision check (which works on English labels) still applies."""
    def repl(m):
        word = m.group(1)
        label = "Article" if word in ("آرٹیکل", "آرٹیکلز") else "Section"
        return f"{label} {m.group(2).translate(_EASTERN_DIGITS)}"
    return _NATIVE_CITE_RE.sub(repl, text)


def localize_citations(text: str, lang: str) -> str:
    """Converts the verified English citations in the answer into the user's language."""
    if lang == "english" or lang not in LANGS:
        return text
    cfg = LANGS[lang]

    def label_of(word: str) -> str:
        return cfg["article_label"] if word.lower() == "article" else cfg["section_label"]

    def of_word(word: str) -> str:
        return cfg["of_article"] if word.lower() == "article" else cfg["of_section"]

    def full_repl(m):
        law = cfg["law_short_const"] if m.group("const") else cfg["law_short_crpc"]
        word = m.group("label")
        out = f"{law} {of_word(word)} {label_of(word)} {m.group('num')}"
        if m.group("b1") or m.group("b2") or m.group("b3"):
            out = f"**{out}**"
        return out

    text = _FULL_CITE_RE.sub(full_repl, text)
    text = _BARE_CITE_RE.sub(lambda m: f"{label_of(m.group(1))} {m.group(2)}", text)
    return text


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

# Small in-memory answer cache (saves LLM quota on repeated questions)
CACHE_TTL_SECONDS = 3600
CACHE_MAX_ITEMS = 300
_answer_cache: "OrderedDict[Tuple[str, str], Tuple[float, dict]]" = OrderedDict()
_cache_lock = threading.Lock()


class ChatRequest(BaseModel):
    query: str
    language: Optional[str] = "english"


class ChatResponse(BaseModel):
    reply: str
    reference: Optional[str] = None
    disclaimer: str = SHORT_DISCLAIMER
    language: Optional[str] = None


def cache_key(lang: str, query: str) -> Tuple[str, str]:
    return (lang, re.sub(r"\s+", " ", (query or "").lower()).strip())


def cache_get(lang: str, query: str) -> Optional[dict]:
    key = cache_key(lang, query)
    with _cache_lock:
        item = _answer_cache.get(key)
        if not item:
            return None
        ts, data = item
        if time.time() - ts > CACHE_TTL_SECONDS:
            _answer_cache.pop(key, None)
            return None
        _answer_cache.move_to_end(key)
        return dict(data)


def cache_set(lang: str, query: str, data: dict) -> None:
    key = cache_key(lang, query)
    with _cache_lock:
        _answer_cache[key] = (time.time(), dict(data))
        _answer_cache.move_to_end(key)
        while len(_answer_cache) > CACHE_MAX_ITEMS:
            _answer_cache.popitem(last=False)


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
        f"LLM enabled: {llm_enabled()} (chain: {', '.join(chain_names(False)) or 'none'})"
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


# ---------------------------------------------------------------------------
# LLM provider chain (Gemini + Groq, per-model cooldowns)
# ---------------------------------------------------------------------------
def build_chain(light: bool = False) -> List[dict]:
    """Ordered list of {provider, base_url, api_key, model}. 'light' puts small cheap models first."""
    groq_chain: List[dict] = []
    if LLM_API_KEY and LLM_BASE_URL:
        is_groq = "groq.com" in LLM_BASE_URL
        main_models = [LLM_MODEL] + LLM_FALLBACK_MODELS + (LLM_EXTRA_MODELS if is_groq else [])
        models = _dedupe((LLM_LIGHT_MODELS if (light and is_groq) else []) + main_models)
        provider = "groq" if is_groq else "primary"
        groq_chain = [
            {"provider": provider, "base_url": LLM_BASE_URL, "api_key": LLM_API_KEY, "model": m}
            for m in models
        ]

    gemini_chain: List[dict] = []
    if GEMINI_API_KEY:
        models = _dedupe((GEMINI_LIGHT_MODELS if light else []) + GEMINI_MODELS)
        gemini_chain = [
            {"provider": "gemini", "base_url": GEMINI_BASE_URL, "api_key": GEMINI_API_KEY, "model": m}
            for m in models
        ]

    if LLM_PRIORITY == "groq_first":
        return groq_chain + gemini_chain
    return gemini_chain + groq_chain


def chain_names(light: bool = False) -> List[str]:
    return [f"{e['provider']}:{e['model']}" for e in build_chain(light)]


def llm_enabled() -> bool:
    return bool((LLM_BASE_URL and LLM_API_KEY) or GEMINI_API_KEY)


def _parse_retry_seconds(resp: "httpx.Response") -> float:
    try:
        return max(1.0, float(resp.headers.get("retry-after")))
    except (TypeError, ValueError):
        pass
    text = resp.text or ""
    m_ms = re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*ms", text, re.IGNORECASE)
    if m_ms:
        return max(1.0, float(m_ms.group(1)) / 1000.0)
    m = re.search(r"try again in\s+(?:(\d+)h)?(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)s)?", text, re.IGNORECASE)
    if m and any(m.groups()):
        h, mi, s = (float(x) if x else 0.0 for x in m.groups())
        return max(1.0, h * 3600 + mi * 60 + s)
    return 25.0


def _set_cooldown(key: str, seconds: float) -> None:
    model_cooldown[key] = time.time() + max(1.0, min(seconds, 6 * 3600))


def _call_single(entry: dict, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
    """One request to one model. Sets a cooldown on failure so rate-limited models are skipped next time."""
    global last_llm_error
    model_name = entry["model"]
    key = f"{entry['provider']}:{model_name}"
    body = {
        "model": model_name,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    lower_name = model_name.lower()
    if "gpt-oss" in lower_name or lower_name.startswith("gemini"):
        body["reasoning_effort"] = "low"

    for attempt in range(2):
        try:
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                resp = client.post(
                    f"{entry['base_url'].rstrip('/')}/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {entry['api_key']}",
                    },
                    json=body,
                )
        except Exception as exc:
            last_llm_error = f"{key} request failed: {exc}"
            print(last_llm_error)
            _set_cooldown(key, 5.0)
            return None

        if resp.status_code == 200:
            try:
                data = resp.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            except Exception:
                content = ""
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            if content:
                return content
            last_llm_error = f"{key}: empty content (token limit?)"
            print(last_llm_error)
            _set_cooldown(key, 5.0)
            return None

        text_l = (resp.text or "").lower()
        last_llm_error = f"{key} HTTP {resp.status_code}: {(resp.text or '')[:300]}"
        print(f"LLM API error -> {last_llm_error}")

        if resp.status_code == 400 and "reasoning" in text_l and "reasoning_effort" in body and attempt == 0:
            body.pop("reasoning_effort", None)
            continue
        if resp.status_code == 429:
            _set_cooldown(key, _parse_retry_seconds(resp))
        elif resp.status_code == 413:
            _set_cooldown(key, 300.0)  # request too big for this model's per-minute limit
        elif resp.status_code == 404 or (
            resp.status_code == 400
            and any(w in text_l for w in ("not found", "decommissioned", "does not exist", "deprecated", "model_not_found"))
        ):
            _set_cooldown(key, 3600.0)  # model name no longer valid: stop trying for a while
        elif resp.status_code in (401, 403):
            _set_cooldown(key, 600.0)
        else:
            _set_cooldown(key, 10.0)
        return None
    return None


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int, light: bool = False) -> Optional[str]:
    """Tries every configured model in order; skips models that are cooling down after a rate limit."""
    global last_llm_error
    last_llm_error = ""
    chain = build_chain(light)
    if not chain:
        last_llm_error = "No LLM provider configured (set GROQ_API_KEY and/or GEMINI_API_KEY)."
        return None

    for round_no in range(2):
        now = time.time()
        for entry in chain:
            key = f"{entry['provider']}:{entry['model']}"
            if model_cooldown.get(key, 0.0) > now:
                continue
            result = _call_single(entry, system_prompt, user_prompt, max_tokens)
            if result:
                return result
            now = time.time()

        if round_no == 0:
            now = time.time()
            waits = [
                model_cooldown[f"{e['provider']}:{e['model']}"] - now
                for e in chain
                if model_cooldown.get(f"{e['provider']}:{e['model']}", 0.0) > now
            ]
            if waits and min(waits) <= LLM_MAX_WAIT_SECONDS:
                time.sleep(min(waits) + 0.3)
                continue
        break
    return None


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
    out = call_llm(system, query, 400, light=True)
    if not out:
        return []
    lines = []
    for ln in out.splitlines():
        ln = re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip()
        if 3 <= len(ln) <= 200:
            lines.append(ln)
    return lines[:5]


def prepare_search_queries(query: str, lang: str) -> Tuple[str, List[str]]:
    """Returns (english_query, expansions). Urdu / Roman Urdu questions are translated to English for retrieval,
    because the indexed books and the embedding model are English."""
    if lang == "english":
        return query, expand_query(query)

    if not llm_enabled():
        return glossary_translate(query), []

    label = "Urdu (Arabic script)" if lang == "urdu" else "Roman Urdu (Urdu written in English letters)"
    system = (
        "You help search the Constitution of Pakistan (1973) and the Code of Criminal Procedure (1898). "
        f"The user's question is written in {label}. "
        "Line 1: translate the question into plain, natural English (one line, no label). "
        "Lines 2-6: write 5 short English search queries (max 16 words each). Queries 1-3 must use the formal legal "
        "vocabulary and the section/article HEADING wording those books use (for example: 'safeguards as to arrest and "
        "detention', 'protection against self-incrimination', 'mode of searching women'). Queries 4-5 must be written as "
        "the likely WORDING of the legal rule itself, in the style of an old statute. Cover different legal angles. "
        "Output exactly 6 lines, one per line, no numbering, no labels, no explanations."
    )
    out = call_llm(system, query, 500, light=True)
    lines: List[str] = []
    if out:
        for ln in out.splitlines():
            ln = re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip()
            ln = re.sub(r"^(english|translation)\s*:\s*", "", ln, flags=re.IGNORECASE).strip()
            if 3 <= len(ln) <= 300:
                lines.append(ln)
    if not lines:
        return glossary_translate(query), []

    english = lines[0]
    expansions = [ln for ln in lines[1:] if len(ln) <= 200][:5]
    if not expansions:
        expansions = expand_query(english)
    return english, expansions


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
        # Roman Urdu / Urdu
        "tafseel", "tafsil", "wazahat", "mukammal", "tafseer", "تفصیل", "وضاحت", "مکمل", "طریقہ کار",
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


def build_reference(reply_text: str, passages: List[dict], lang: str = "english") -> Optional[str]:
    """Reference lines are built ONLY from provisions the answer cites and that really exist in the retrieved text.
    reply_text must still contain the English 'Article N' / 'Section N' labels. Output is in the user's language."""
    cfg = LANGS.get(lang, LANGS["english"])
    refs = []
    for kind, num in extract_citations(reply_text):
        p = find_provision_passage(num, kind, passages)
        if p:
            title = re.sub(r"\.pdf$", "", p["book_title"], flags=re.IGNORECASE)
            if lang == "english":
                label = "Article" if kind == "constitution" else "Section"
                name = title
            else:
                label = cfg["article_label"] if kind == "constitution" else cfg["section_label"]
                bk = book_kind(p["book_title"])
                if bk == "constitution":
                    name = cfg["const_name"]
                elif bk == "crpc":
                    name = cfg["crpc_name"]
                else:
                    name = title
            refs.append(f"{name} - {label} {num}")
    refs = list(dict.fromkeys(refs))
    return " | ".join(refs[:4]) if refs else None


def build_fallback_answer(passages: List[dict], lang: str) -> dict:
    """Used only when every LLM is unavailable: show the most relevant excerpts instead of an error message."""
    cfg = LANGS[lang]
    ranked = sorted(passages, key=lambda p: p.get("final_score", 0.0), reverse=True)
    top = [p for p in ranked if p.get("final_score", 0.0) > 0][:2] or ranked[:2]
    blocks = []
    for p in top:
        kind = book_kind(p["book_title"])
        if kind == "constitution":
            name = cfg["const_name"]
        elif kind == "crpc":
            name = cfg["crpc_name"]
        else:
            name = p["book_title"]
        txt = p["cleaned"]
        if len(txt) > 900:
            cut = txt[:900]
            last = max(cut.rfind(". "), cut.rfind("; "))
            txt = (cut[: last + 1] if last > 400 else cut) + " ..."
        blocks.append(f"**{name}**\n{txt}")
    reply = cfg["fallback_intro"] + "\n\n" + "\n\n".join(blocks)
    return {"status": "fallback", "reply": reply, "reference": None}


def generate_with_llm(query: str, passages: List[dict], lang: str = "english", english_query: str = "") -> dict:
    """Returns {"status": "ok"|"out"|"error", "reply": str, "reference": Optional[str]}."""
    if not llm_enabled():
        print(f"LLM skipped: no provider configured (LLM_BASE_URL={bool(LLM_BASE_URL)}, "
              f"LLM_API_KEY={bool(LLM_API_KEY)}, GEMINI_API_KEY={bool(GEMINI_API_KEY)})")
        return {"status": "error", "reply": "", "reference": None}

    cfg = LANGS.get(lang, LANGS["english"])
    detailed = is_detailed_query(query) or is_detailed_query(english_query)
    if lang == "urdu":
        max_tokens = 3000 if detailed else 2200
    elif lang == "roman_urdu":
        max_tokens = 2400 if detailed else 1600
    else:
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
        f"You are a Pakistani Legal AI Assistant. {cfg['instruction']} "
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
            f"7. STRUCTURE (use exactly these bold headings):\n**{cfg['most_relevant']}**\nThe single most relevant provision in bold "
            f"with a clear explanation (3-4 sentences) in simple {cfg['simple_name']}.\n**{cfg['supported']}**\nOther relevant provisions in "
            f"bold, each with a short explanation of how it relates. If there are none, write: {cfg['no_other']}"
        )
    else:
        rules += (
            f"7. LENGTH: short, clear and direct in simple {cfg['simple_name']} (3-5 sentences). Start with '{cfg['yes']}' or "
            f"'{cfg['no']}' (or '{cfg['generally_no']}') for yes/no questions ('Can...', 'Does...', 'Is...'), then explain "
            "with the exact provision."
        )

    def make_prompt(extra: str = "") -> str:
        prompt = f"Excerpts:\n{context_text}\n\nQuestion: {query}"
        if english_query and english_query.strip().lower() != query.strip().lower():
            prompt += f"\nEnglish meaning of the question: {english_query}"
        return prompt + extra

    user_prompt = make_prompt()

    reply_text = ""
    for attempt in range(2):
        content = call_llm(rules, user_prompt, max_tokens)
        if not content:
            return {"status": "error", "reply": "", "reference": None}
        if "OUT_OF_SCOPE" in content[:80]:
            return {"status": "out", "reply": cfg["out_of_scope"], "reference": None}

        reply_text = normalize_reply_formatting(content)
        if lang != "english":
            # If the model wrote native labels (دفعہ / آرٹیکل / Dafa) itself, restore English labels for verification.
            reply_text = to_english_labels(reply_text)
        bad = [
            f"{'Article' if k == 'constitution' else 'Section'} {n}"
            for k, n in extract_citations(reply_text)
            if find_provision_passage(n, k, passages) is None
        ]
        if not bad:
            break
        user_prompt = make_prompt(
            f"\n\nWARNING: your previous answer cited {', '.join(bad)}, which does NOT appear in the excerpts. "
            "Answer again citing only provisions whose number actually appears in the excerpts and describe each "
            "provision only by what its own text says."
        )

    # Verified in English above; now present reference and citations in the user's language.
    reference = build_reference(reply_text, passages, lang)
    final_reply = localize_citations(reply_text, lang)
    return {"status": "ok", "reply": final_reply, "reference": reference}


@app.get("/health")
def health_check():
    count = collection.count() if collection is not None else 0
    return {
        "status": "ok",
        "version": "v8-localized-citations",
        "collection": COLLECTION_NAME,
        "indexed_chunks": count,
        "llm_enabled": llm_enabled(),
        "llm_model": LLM_MODEL if (LLM_API_KEY and LLM_BASE_URL) else None,
        "gemini_enabled": bool(GEMINI_API_KEY),
        "languages": ["english", "urdu", "roman_urdu"],
        "env_file_loaded": ENV_PATH.exists(),
    }


@app.get("/llm-test")
def llm_test():
    """Open this URL in a browser to see whether the AI services (Gemini/Groq) are working, and the exact error if not."""
    out = call_llm("Reply with exactly the word: OK", "ping", 300, light=True)
    now = time.time()
    return {
        "ok": bool(out),
        "reply": (out or "")[:50],
        "models_tried_in_order": chain_names(False),
        "light_models_in_order": chain_names(True),
        "cooling_down_seconds": {
            k: round(v - now) for k, v in model_cooldown.items() if v > now
        },
        "last_error": last_llm_error,
    }


GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|salam|salaam|aoa|assalam[\s-]?o[\s-]?alaikum|assalamu[\s-]?alaikum|assalamualaikum|"
    r"good (morning|evening|afternoon)|thanks|thank you|shukriya|shukria|jazak[\s-]?allah|"
    r"السلام علیکم|سلام|ہیلو|شکریہ)\W*$",
    re.IGNORECASE,
)


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(payload: ChatRequest):
    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")

    lang = detect_language(query)
    cfg = LANGS[lang]

    if GREETING_RE.match(query):
        return ChatResponse(
            reply=cfg["greeting"],
            reference=None,
            disclaimer=cfg["disclaimer"],
            language=lang,
        )

    if collection is None or model is None:
        raise HTTPException(status_code=503, detail="Backend services are starting up.")

    cached = cache_get(lang, query)
    if cached:
        print(f"Cache hit ({lang})")
        return ChatResponse(**cached)

    try:
        english_query, expansions = prepare_search_queries(query, lang)
        queries = [english_query] + expansions
        print(f"Language={lang} | Search queries: {queries}")
        passages = hybrid_retrieve(queries, top_k=7)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ChromaDB query failed: {exc}")

    if not passages or passages[0].get("best_vec", 0.0) < 0.2:
        return ChatResponse(
            reply=cfg["out_of_scope"], reference=None, disclaimer=cfg["disclaimer"], language=lang
        )

    result = generate_with_llm(query, passages, lang, english_query)
    if result["status"] == "out":
        try:
            wide_passages = hybrid_retrieve(queries, top_k=12, wide=True)
            if wide_passages:
                print("Retrying with wider context before declaring out of scope.")
                retry = generate_with_llm(query, wide_passages, lang, english_query)
                if retry["status"] != "error":
                    result = retry
        except Exception as exc:
            print(f"Wide retry failed: {exc}")

    if result["status"] == "error":
        # All models unavailable: show the most relevant law excerpts instead of a "busy" message.
        print(f"All LLMs unavailable, using excerpt fallback. Last error: {last_llm_error}")
        result = build_fallback_answer(passages, lang)

    print(f"Answer status={result['status']} reference={result['reference']}")
    response_data = {
        "reply": result["reply"],
        "reference": result["reference"],
        "disclaimer": cfg["disclaimer"],
        "language": lang,
    }
    if result["status"] in ("ok", "out"):
        cache_set(lang, query, response_data)
    return ChatResponse(**response_data)
