// book_ingest/ingest.mjs
import fs from "fs";
import path from "path";
import { ChromaClient } from "chromadb";
import { pipeline } from "@huggingface/transformers";
import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf.mjs";

const CHROMA_URL = process.env.CHROMA_URL || "http://localhost:8000";
const COLLECTION_NAME = process.env.CHROMA_COLLECTION || "legal_book_chunks";
const BOOKS_FOLDER = path.resolve("..", "books_raw");
const MAX_CHUNK_CHARS = 1100;
const OVERLAP_CHARS = 220;

const parsedChromaUrl = new URL(CHROMA_URL);
const chroma = new ChromaClient({
  host: parsedChromaUrl.hostname,
  port: parsedChromaUrl.port ? Number(parsedChromaUrl.port) : (parsedChromaUrl.protocol === "https:" ? 443 : 80),
  ssl: parsedChromaUrl.protocol === "https:",
});

async function extractPdfText(pdfPath) {
  const data = new Uint8Array(fs.readFileSync(pdfPath));
  const pdf = await pdfjsLib.getDocument({ data }).promise;
  let fullText = "";

  for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
    const page = await pdf.getPage(pageNum);
    const content = await page.getTextContent();
    const pageText = content.items.map((item) => item.str).join(" ");
    fullText += `\n[Page ${pageNum}] ${pageText}`;
  }

  return fullText;
}

// Split along numbered Article/Section boundaries while keeping headings attached to their clauses
function splitIntoLegalChunks(rawText) {
  const cleanText = rawText
    .replace(/Page\s+\d+\s+of\s+\d+/gi, " ")
    .replace(/\s+/g, " ")
    .trim();

  // Split right before numbered provisions like " 1. ", " 2. ", " 4. ", " 154. "
  const sections = cleanText.split(/(?=\s\d{1,3}[A-Z]?\.\s+[A-Z])/);
  const chunks = [];
  let buffer = "";

  for (const sec of sections) {
    const trimmed = sec.trim();
    if (!trimmed) continue;

    if ((buffer + " " + trimmed).length <= MAX_CHUNK_CHARS) {
      buffer = buffer ? `${buffer} ${trimmed}` : trimmed;
    } else {
      if (buffer.length > 40) {
        chunks.push(buffer);
      }
      if (trimmed.length <= MAX_CHUNK_CHARS) {
        // Carry trailing overlap from previous buffer so boundary context is preserved
        const tail = buffer.slice(-OVERLAP_CHARS).trim();
        buffer = tail ? `${tail} ${trimmed}` : trimmed;
      } else {
        // Long section: sliding window with overlap
        let start = 0;
        while (start < trimmed.length) {
          const end = Math.min(start + MAX_CHUNK_CHARS, trimmed.length);
          const piece = trimmed.slice(start, end).trim();
          if (piece.length > 40) chunks.push(piece);
          if (end >= trimmed.length) break;
          start += MAX_CHUNK_CHARS - OVERLAP_CHARS;
        }
        buffer = "";
      }
    }
  }

  if (buffer.length > 40) {
    chunks.push(buffer);
  }

  return chunks;
}

function detectProvisionNumbers(text) {
  const matches = [...text.matchAll(/\b(\d{1,3}[A-Z]?)\.\s+[A-Z]/g)].map((m) => m[1]);
  const unique = [...new Set(matches)];
  return unique.length > 0 ? unique.slice(0, 6).join(", ") : "";
}

function makeSafeId(bookTitle, index) {
  const slug = bookTitle
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
  return `${slug || "book"}_chunk_${index}`;
}

async function run() {
  if (!fs.existsSync(BOOKS_FOLDER)) {
    console.error(`Books folder not found: ${BOOKS_FOLDER}`);
    process.exit(1);
  }

  const pdfFiles = fs
    .readdirSync(BOOKS_FOLDER)
    .filter((file) => file.toLowerCase().endsWith(".pdf"));

  if (pdfFiles.length === 0) {
    console.log(`No .pdf files found in ${BOOKS_FOLDER}.`);
    return;
  }

  console.log(`Connecting to ChromaDB at ${CHROMA_URL}...`);
  const collection = await chroma.getOrCreateCollection({
    name: COLLECTION_NAME,
    metadata: { "hnsw:space": "cosine" },
  });

  console.log("Loading local embedding model (Xenova/all-MiniLM-L6-v2)...");
  const extractor = await pipeline(
    "feature-extraction",
    "Xenova/all-MiniLM-L6-v2"
  );

  for (const fileName of pdfFiles) {
    const filePath = path.join(BOOKS_FOLDER, fileName);
    const bookTitle = path.basename(fileName, ".pdf");

    console.log(`\nProcessing "${bookTitle}.pdf"...`);
    const pdfText = await extractPdfText(filePath);
    const chunks = splitIntoLegalChunks(pdfText);
    console.log(`Total legal chunks: ${chunks.length}`);

    try {
      await collection.delete({ where: { book_title: bookTitle } });
    } catch {
      // Ignore if no prior documents exist
    }

    const batchSize = 25;
    for (let startIdx = 0; startIdx < chunks.length; startIdx += batchSize) {
      const batchChunks = chunks.slice(startIdx, startIdx + batchSize);
      const ids = [];
      const embeddings = [];
      const documents = [];
      const metadatas = [];

      for (let offset = 0; offset < batchChunks.length; offset++) {
        const chunkIndex = startIdx + offset;
        const text = batchChunks[offset];

        const output = await extractor(text, {
          pooling: "mean",
          normalize: true,
        });

        ids.push(makeSafeId(bookTitle, chunkIndex));
        embeddings.push(Array.from(output.data));
        documents.push(text);
        metadatas.push({
          book_title: bookTitle,
          chunk_index: chunkIndex,
          source_file: fileName,
          provisions: detectProvisionNumbers(text),
        });
      }

      await collection.upsert({
        ids,
        embeddings,
        documents,
        metadatas,
      });

      const doneCount = Math.min(startIdx + batchSize, chunks.length);
      console.log(`Upserted ${doneCount}/${chunks.length} chunks for "${bookTitle}"`);
    }
  }

  console.log(`\nChromaDB legal ingestion complete into collection "${COLLECTION_NAME}"!`);
}

run().catch((err) => {
  console.error("Ingestion error:", err);
  process.exit(1);
});