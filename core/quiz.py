"""Quiz generation (local LLM, strict JSON, validated with Pydantic) and grading."""
from __future__ import annotations

import json
import random
import uuid

import ollama
from pydantic import BaseModel, ValidationError, field_validator, model_validator

from core.config import COLLECTION, DEFAULT_CLASS_LEVEL, LLM_MODEL, LLM_NUM_CTX
from core.progress import save_attempt
from core.retriever import build_payload_filter, get_qdrant_client

MAX_CHUNKS_IN_PROMPT = 4   # keep the prompt small for small local models
MAX_ATTEMPTS = 3           # LLM calls allowed to collect enough valid questions
_QUIZZES: dict[str, dict] = {}   # quizzes waiting to be graded (in memory)

EXAMPLE_JSON = (
    '{"questions": [{"question": "...", "correct_answer": "...", '
    '"wrong_answers": ["...", "...", "..."], '
    '"explanation": "one short sentence giving the reason", "page": 1}]}'
)


class QuizQuestion(BaseModel):
    """One question: the model gives the right answer as TEXT plus 3 wrong answers.
    The code builds and shuffles the options itself, so a wrong index can't happen."""
    question: str
    correct_answer: str
    wrong_answers: list[str]
    explanation: str = ""
    page: int | None = None

    @field_validator("page", mode="before")
    @classmethod
    def lenient_page(cls, v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    @model_validator(mode="after")
    def check_answers(self) -> "QuizQuestion":
        self.question = self.question.strip()
        self.correct_answer = self.correct_answer.strip()
        self.wrong_answers = [str(a).strip() for a in self.wrong_answers]
        if not self.question or not self.correct_answer:
            raise ValueError("question and correct_answer are required")
        if len(self.wrong_answers) != 3 or any(not a for a in self.wrong_answers):
            raise ValueError("need exactly 3 non-empty wrong answers")
        options = [self.correct_answer] + self.wrong_answers
        if len({o.lower() for o in options}) != 4:
            raise ValueError("all 4 options must be different")
        return self


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


def _build_question(q: QuizQuestion) -> dict:
    """Mix the right answer in with the wrong ones and record where it ended up."""
    options = [q.correct_answer] + q.wrong_answers
    random.shuffle(options)
    return {
        "question": q.question,
        "options": options,
        "correct_index": options.index(q.correct_answer),
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
            "Rules: correct_answer is the one answer stated in the excerpts. "
            "wrong_answers are exactly 3 believable but incorrect answers, all different from "
            "correct_answer and from each other. All four options must be similar in length and "
            "style, and short (under 12 words). explanation gives the reason in one sentence "
            "and must not simply repeat the answer. page is the page number shown in the excerpt."
        )
        resp = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format="json",
            options={"temperature": 0.4, "num_ctx": LLM_NUM_CTX},
        )
        for q in _parse_questions(resp["message"]["content"]):
            key = q.question.lower()
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
        "questions": [_build_question(q) for q in questions[:n]],
    }
    _QUIZZES[quiz_id] = quiz
    if len(_QUIZZES) > 200:                    # don't grow forever
        _QUIZZES.pop(next(iter(_QUIZZES)))
    return quiz


def _clean(text: str) -> str:
    return text.strip().rstrip(".").strip()


def _feedback(correct: bool, right_text: str, explanation: str) -> str:
    # Skip the explanation if it only repeats the answer.
    if explanation and _clean(explanation).lower() == _clean(right_text).lower():
        explanation = ""
    head = "Correct!" if correct else f"Not quite. The right answer is: {_clean(right_text)}."
    return f"{head} {explanation}".strip()


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
        results.append({
            "question": q["question"], "chosen": chosen, "correct_index": q["correct_index"],
            "correct": correct, "feedback": _feedback(correct, right_text, q["explanation"]),
            "page": q["page"],
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
    raw_n = input("How many questions [3]: ").strip()
    n = int(raw_n) if raw_n.isdigit() and int(raw_n) > 0 else 3
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