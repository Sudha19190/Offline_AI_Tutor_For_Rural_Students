"""Quiz generation (local LLM, strict JSON, validated with Pydantic) and grading."""
from __future__ import annotations

import json
import random
import uuid

import ollama
from pydantic import BaseModel, ValidationError, field_validator

from core.config import COLLECTION, DEFAULT_CLASS_LEVEL, LLM_MODEL, LLM_NUM_CTX
from core.progress import save_attempt
from core.retriever import build_payload_filter, get_qdrant_client

MAX_CHUNKS_IN_PROMPT = 4   # keep the prompt small for small local models
MAX_ATTEMPTS = 3           # LLM calls allowed to collect enough valid questions
_QUIZZES: dict[str, dict] = {}   # quizzes waiting to be graded (in memory)

EXAMPLE_JSON = (
    '{"questions": [{"question": "...", "options": ["...", "...", "...", "..."], '
    '"correct_index": 0, "explanation": "one short sentence", "page": 1}]}'
)


class QuizQuestion(BaseModel):
    """One multiple-choice question; anything that doesn't fit this shape is dropped."""
    question: str
    options: list[str]
    correct_index: int
    explanation: str = ""
    page: int | None = None

    @field_validator("options")
    @classmethod
    def exactly_four_distinct(cls, v: list[str]) -> list[str]:
        v = [str(o).strip() for o in v]
        if len(v) != 4 or len(set(v)) != 4 or any(not o for o in v):
            raise ValueError("need exactly 4 distinct, non-empty options")
        return v

    @field_validator("correct_index")
    @classmethod
    def index_in_range(cls, v: int) -> int:
        if not 0 <= v <= 3:
            raise ValueError("correct_index must be 0-3")
        return v


def get_chapter_chunks(subject: str, chapter: str) -> list[dict]:
    """All stored chunks of one chapter, ordered by page."""
    client = get_qdrant_client()
    try:
        points, _ = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=build_payload_filter(subject=subject, chapter=chapter),
            limit=1000, with_payload=True, with_vectors=False,
        )
    finally:
        client.close()
    return sorted((p.payload for p in points if p.payload), key=lambda c: c.get("page", 0))


def _parse_questions(raw: str) -> list[QuizQuestion]:
    """Parse the model's JSON and keep only the questions that pass validation."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data.get("questions", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    valid = []
    for item in items:
        try:
            valid.append(QuizQuestion.model_validate(item))
        except ValidationError:
            continue
    return valid


def _shuffle_options(q: QuizQuestion) -> dict:
    """Small models love putting the answer first, so shuffle and re-find the index."""
    correct_text = q.options[q.correct_index]
    options = q.options[:]
    random.shuffle(options)
    return {
        "question": q.question.strip(),
        "options": options,
        "correct_index": options.index(correct_text),
        "explanation": q.explanation.strip(),
        "page": q.page,
    }


def generate_quiz(subject: str, chapter: str, n: int = 5, class_level: str | None = None) -> dict:
    """Generate n multiple-choice questions from a chapter's own text."""
    class_level = class_level or DEFAULT_CLASS_LEVEL
    chunks = get_chapter_chunks(subject, chapter)
    if not chunks:
        raise ValueError(f"No content found for {subject} / {chapter}. Ingest the textbook first.")

    pool = random.sample(chunks, min(MAX_CHUNKS_IN_PROMPT, len(chunks)))
    pool.sort(key=lambda c: c.get("page", 0))
    excerpts = "\n\n".join(f"[Page {c['page']}] {c['text'][:800]}" for c in pool)
    system = (
        f"You write clear multiple-choice quiz questions for {class_level} students. "
        "Use ONLY the textbook excerpts given. Reply with JSON only."
    )

    questions: list[QuizQuestion] = []
    seen: set[str] = set()
    for _ in range(MAX_ATTEMPTS):
        needed = n - len(questions)
        if needed <= 0:
            break
        user = (
            f"Textbook excerpts:\n{excerpts}\n\n"
            f"Write {needed} multiple-choice questions based only on these excerpts.\n"
            f"Return JSON in exactly this shape:\n{EXAMPLE_JSON}\n"
            "Rules: exactly 4 different options; correct_index is the position (0 to 3) of the "
            "one right option; page is the page number shown in the excerpt."
        )
        resp = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format="json",
            options={"temperature": 0.4, "num_ctx": LLM_NUM_CTX},
        )
        for q in _parse_questions(resp["message"]["content"]):
            key = q.question.strip().lower()
            if key not in seen:
                seen.add(key)
                questions.append(q)

    if not questions:
        raise RuntimeError("Could not generate a valid quiz. Please try again.")

    quiz_id = uuid.uuid4().hex[:12]
    quiz = {
        "quiz_id": quiz_id,
        "subject": subject,
        "chapter": chapter,
        "questions": [_shuffle_options(q) for q in questions[:n]],
    }
    _QUIZZES[quiz_id] = quiz
    if len(_QUIZZES) > 200:                    # don't grow forever
        _QUIZZES.pop(next(iter(_QUIZZES)))
    return quiz


def grade(quiz_id: str, answers: list[int | None], student_id: int | None = None) -> dict:
    """Grade a submitted quiz. answers[i] is the chosen option index (0-3) or None if skipped."""
    quiz = _QUIZZES.get(quiz_id)
    if quiz is None:
        raise KeyError("Quiz not found or expired. Please generate a new quiz.")
    questions = quiz["questions"]
    if len(answers) != len(questions):
        raise ValueError(f"Expected {len(questions)} answers, got {len(answers)}.")

    results = []
    for q, chosen in zip(questions, answers):
        correct = chosen == q["correct_index"]
        right_text = q["options"][q["correct_index"]]
        if correct:
            feedback = f"Correct! {q['explanation']}".strip()
        else:
            feedback = f"Not quite. The right answer is: {right_text}. {q['explanation']}".strip()
        results.append({
            "question": q["question"], "chosen": chosen, "correct_index": q["correct_index"],
            "correct": correct, "feedback": feedback, "page": q["page"],
        })

    score = sum(r["correct"] for r in results)
    attempt_id = None
    if student_id is not None:
        attempt_id = save_attempt(student_id, quiz["subject"], quiz["chapter"], results)
    return {
        "score": score, "total": len(results),
        "percent": round(100 * score / len(results)) if results else 0,
        "results": results, "attempt_id": attempt_id,
    }


if __name__ == "__main__":
    from core.progress import get_chapter_accuracy, get_or_create_student

    subject = input("Subject [Science]: ").strip() or "Science"
    chapter = input("Chapter [Crop Production and Management]: ").strip() or "Crop Production and Management"
    n = int(input("How many questions [3]: ").strip() or 3)
    name = input("Your name [Test Student]: ").strip() or "Test Student"
    student_id = get_or_create_student(name)

    print("\nGenerating quiz (can take a minute on a small local model)...")
    quiz = generate_quiz(subject, chapter, n)

    answers: list[int | None] = []
    for i, q in enumerate(quiz["questions"], 1):
        print(f"\nQ{i}. {q['question']}")
        for j, opt in enumerate(q["options"], 1):
            print(f"   {j}. {opt}")
        pick = input("Your answer (1-4, Enter to skip): ").strip()
        answers.append(int(pick) - 1 if pick in {"1", "2", "3", "4"} else None)

    result = grade(quiz["quiz_id"], answers, student_id)
    print(f"\nScore: {result['score']}/{result['total']} ({result['percent']}%)")
    for r in result["results"]:
        print(" -", "OK" if r["correct"] else "X ", r["feedback"])
    print("\nProgress so far:", get_chapter_accuracy(student_id))