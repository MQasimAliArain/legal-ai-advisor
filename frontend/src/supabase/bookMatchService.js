import { supabase } from "./supabaseClient";

const SHORT_DISCLAIMER =
  "Disclaimer: For informational purposes only; not formal legal advice.";

const MATCH_COUNT = 4;

function cleanChunkContent(rawContent) {
  return (rawContent || "")
    .replace(/\[Page\s+\d+\]\s*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildFallbackKeywords(question) {
  const stopWords = new Set([
    "what", "is", "the", "a", "an", "and", "or", "of", "in", "to", "for",
    "on", "with", "how", "does", "do", "that", "this", "are", "be", "by",
    "from", "as", "at", "it", "can", "when", "where", "which", "who"
  ]);

  const words = (question || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !stopWords.has(w));

  return Array.from(new Set(words)).join(" ");
}

export async function getAnswerFromSupabaseBooks(question) {
  const cleanQuestion = (question || "").trim();

  if (!cleanQuestion) {
    return {
      answer: "Please enter a legal question.",
      reference: null,
      disclaimer: SHORT_DISCLAIMER,
    };
  }

  let { data: matches, error } = await supabase.rpc("search_legal_chunks", {
    search_query: cleanQuestion,
    match_count: MATCH_COUNT,
  });

  if (error) {
    throw new Error(`Supabase search failed: ${error.message}`);
  }

  if (!matches || matches.length === 0) {
    const keywordQuery = buildFallbackKeywords(cleanQuestion);
    if (keywordQuery) {
      const fallbackRes = await supabase.rpc("search_legal_chunks", {
        search_query: keywordQuery,
        match_count: MATCH_COUNT,
      });

      if (fallbackRes.error) {
        throw new Error(`Supabase fallback search failed: ${fallbackRes.error.message}`);
      }

      matches = fallbackRes.data || [];
    }
  }

  if (!matches || matches.length === 0) {
    return {
      answer: "No matching answer was found in the uploaded legal books.",
      reference: null,
      disclaimer: SHORT_DISCLAIMER,
    };
  }

  const topMatch = matches[0];
  const formattedAnswer = matches
    .map((match) => cleanChunkContent(match.content))
    .filter(Boolean)
    .join("\n\n---\n\n");

  return {
    answer: formattedAnswer || "No matching answer was found in the uploaded legal books.",
    reference: `${topMatch.book_title}.pdf — Part ${topMatch.chunk_index + 1}`,
    disclaimer: SHORT_DISCLAIMER,
  };
}