"""LLM layer: textbook-grounded answers from a local Ollama model."""
from __future__ import annotations

from typing import Iterator

import ollama

from core.config import DEFAULT_CLASS_LEVEL, DEFAULT_LANGUAGE, LLM_MODEL, SCORE_THRESHOLD, LLM_NUM_CTX 
from core.retriever import retrieve

NOT_FOUND = "I couldn't find this in your textbook. Please ask your teacher or try rephrasing."
SENTINEL = "NOT_FOUND"


def _build_messages(question: str, hits: list[dict], class_level: str, language: str) -> list[dict]:
    context = "\n\n".join(f"[Page {h['page']}] {h['text']}" for h in hits)
    system = (
        f"You are a friendly tutor for {class_level} students. "
        "Answer using ONLY facts from the textbook excerpts provided. "
        "Use simple words and keep the answer to 3-5 sentences. "
        "If you give an example, it must come from the excerpts. Do not invent examples or facts. "
        f"Reply in {language}. "
        f"If the excerpts do not contain the answer, reply with exactly: {SENTINEL}"
    )
    user = f"Textbook excerpts:\n{context}\n\nQuestion: {question}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def _sources(hits: list[dict]) -> list[dict]:
    seen, out = set(), []
    for h in hits:
        key = (h["chapter"], h["page"])
        if key not in seen:
            seen.add(key)
            out.append({"subject": h["subject"], "chapter": h["chapter"], "page": h["page"]})
    return sorted(out, key=lambda s: s["page"])


def stream_answer(question: str, subject: str | None = None, chapter: str | None = None,
                  class_level: str | None = None, language: str | None = None,
                  hybrid: bool = True) -> Iterator[dict]:
    """Yield events: {'type': 'token'|'sources'|'not_found'|'error', ...}."""
    class_level = class_level or DEFAULT_CLASS_LEVEL
    language = language or DEFAULT_LANGUAGE

    hits = retrieve(question, subject, chapter, hybrid=hybrid)
    best = max((h["score"] for h in hits), default=0.0)   # best dense cosine score
    if not hits or best < SCORE_THRESHOLD:
        yield {"type": "not_found", "text": NOT_FOUND}
        return

    messages = _build_messages(question, hits, class_level, language)
    buffer, decided = "", False
    try:
        stream = ollama.chat(model=LLM_MODEL, messages=messages, stream=True,
                             options={"temperature": 0.2})
        for chunk in stream:
            piece = chunk["message"]["content"]
            if not decided:
                # Hold back the first few characters to see if the model says NOT_FOUND.
                buffer += piece
                if len(buffer.lstrip()) < len(SENTINEL):
                    continue
                decided = True
                if buffer.lstrip().startswith(SENTINEL):
                    yield {"type": "not_found", "text": NOT_FOUND}
                    return
                piece = buffer
            yield {"type": "token", "text": piece}
    except Exception as e:  # Ollama not running, model missing, etc.
        yield {"type": "error", "text": f"The language model is not available: {e}"}
        return

    if not decided:  # very short answer that ended before the check
        if not buffer.strip() or buffer.lstrip().startswith(SENTINEL):
            yield {"type": "not_found", "text": NOT_FOUND}
            return
        yield {"type": "token", "text": buffer}

    yield {"type": "sources", "sources": _sources(hits), "best_score": round(best, 3)}


def answer(question: str, **kwargs) -> dict:
    """Non-streaming version, used by the evaluation scripts."""
    text, sources, grounded, best = "", [], True, None
    for ev in stream_answer(question, **kwargs):
        if ev["type"] == "token":
            text += ev["text"]
        elif ev["type"] == "sources":
            sources, best = ev["sources"], ev["best_score"]
        elif ev["type"] in ("not_found", "error"):
            text, grounded = ev["text"], False
    return {"answer": text.strip(), "sources": sources, "grounded": grounded, "best_score": best}


if __name__ == "__main__":
    while True:
        q = input("\nAsk a question (or 'quit'): ").strip()
        if q.lower() == "quit":
            break
        for ev in stream_answer(q):
            if ev["type"] == "token":
                print(ev["text"], end="", flush=True)
            elif ev["type"] == "sources":
                print("\n\nSources:", ", ".join(f"{s['chapter']}, p.{s['page']}" for s in ev["sources"]))
            else:
                print(ev["text"])