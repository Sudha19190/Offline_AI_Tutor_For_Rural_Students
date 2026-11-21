"""Jnana Vistara API: exposes the core/ modules as web endpoints and serves the React app.

Run from the project root:   uvicorn api.main:app --host 0.0.0.0 --port 8000
Test page (Swagger):         http://localhost:8000/docs
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

import ollama
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.config import COLLECTION, LLM_MODEL
from core.llm import stream_answer
from core.progress import get_or_create_student, get_progress
from core.quiz import generate_quiz, grade
from core.retriever import get_embedder, get_qdrant_client

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_embedder()   # load the embedding model once at startup, not on the first question
    yield


app = FastAPI(title="Jnana Vistara API", version="0.1.0", lifespan=lifespan)

# Allows the Vite dev server (port 5173) and other devices on the local network.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- request bodies ----------
class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    subject: str | None = None
    chapter: str | None = None
    class_level: str | None = None
    language: str | None = None
    hybrid: bool = True


class StudentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class QuizRequest(BaseModel):
    subject: str
    chapter: str
    n: int = Field(default=5, ge=1, le=10)
    class_level: str | None = None


class SubmitRequest(BaseModel):
    quiz_id: str
    answers: list[int | None]
    student_id: int | None = None


# ---------- helpers ----------
def _sse(events: Iterator[dict]) -> Iterator[str]:
    """Turn answer events into Server-Sent Events: 'data: {...}' blocks."""
    try:
        for ev in events:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': f'Something went wrong: {e}'})}\n\n"
    yield 'data: {"type": "done"}\n\n'


def _load_catalog() -> dict:
    """Subjects and chapters that are actually stored in the database."""
    client = get_qdrant_client()
    catalog: dict[str, dict[str, dict]] = {}
    try:
        if not client.collection_exists(COLLECTION):
            return {"subjects": []}
        offset = None
        while True:
            points, offset = client.scroll(
                COLLECTION, limit=500, offset=offset, with_payload=True, with_vectors=False
            )
            for p in points:
                pl = p.payload or {}
                chapter = catalog.setdefault(pl.get("subject", "Unknown"), {}).setdefault(
                    pl.get("chapter", "Unknown"),
                    {"class_level": pl.get("class_level", ""), "chunks": 0, "pages": set()},
                )
                chapter["chunks"] += 1
                chapter["pages"].add(pl.get("page"))
            if offset is None:
                break
    finally:
        client.close()
    return {
        "subjects": [
            {
                "name": subject,
                "chapters": [
                    {"name": name, "class_level": c["class_level"],
                     "chunks": c["chunks"], "pages": len(c["pages"])}
                    for name, c in sorted(chapters.items())
                ],
            }
            for subject, chapters in sorted(catalog.items())
        ]
    }


# ---------- endpoints ----------
@app.get("/api/health")
def health() -> dict:
    try:
        installed = [m["model"] for m in ollama.list()["models"]]
        return {"status": "ok", "ollama": True, "model": LLM_MODEL,
                "model_installed": LLM_MODEL in installed}
    except Exception:
        return {"status": "degraded", "ollama": False, "model": LLM_MODEL, "model_installed": False}


@app.get("/api/catalog")
def catalog() -> dict:
    return _load_catalog()


@app.post("/api/students")
def create_student(req: StudentRequest) -> dict:
    """Simple name-based login: returns the student's id (creates the student if new)."""
    try:
        return {"student_id": get_or_create_student(req.name), "name": req.name.strip()}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/ask")
def ask(req: AskRequest) -> StreamingResponse:
    """Stream the answer as Server-Sent Events: token..., then sources (or not_found), then done."""
    events = stream_answer(
        req.question, subject=req.subject, chapter=req.chapter,
        class_level=req.class_level, language=req.language, hybrid=req.hybrid,
    )
    return StreamingResponse(
        _sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/quiz/generate")
def quiz_generate(req: QuizRequest) -> dict:
    # Note: the response includes correct_index so the UI can show instant feedback.
    # This is a study tool, not a secure exam.
    try:
        return generate_quiz(req.subject, req.chapter, req.n, req.class_level)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(503, f"The language model is not available: {e}")


@app.post("/api/quiz/submit")
def quiz_submit(req: SubmitRequest) -> dict:
    try:
        return grade(req.quiz_id, req.answers, req.student_id)
    except KeyError as e:
        raise HTTPException(404, str(e).strip("'\""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/progress/{student_id}")
def progress(student_id: int) -> dict:
    data = get_progress(student_id)
    if data["student_name"] is None:
        raise HTTPException(404, "Student not found.")
    return data


# ---------- serve the built React app (after `npm run build`) ----------
if DIST.exists():
    if (DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        candidate = (DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")