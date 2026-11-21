"""Find a good SCORE_THRESHOLD: in-scope questions should score above it, off-topic below."""
from core.retriever import retrieve

# Edit these to match what YOUR chapter actually covers.
IN_SCOPE = [
    "What is irrigation?",
    "Why do farmers use manure and fertilisers?",
    "How is harvested grain stored?",
    "What are kharif and rabi crops?",
    "What is weeding?",
]
OFF_TOPIC = [
    "Who won the IPL?",
    "What is the capital of France?",
    "Explain Newton's laws of motion.",
    "How do I install Python?",
]


def check(q: str) -> tuple[float, int]:
    hits = retrieve(q)
    if not hits:
        return 0.0, 0
    top = max(hits, key=lambda h: h["score"])
    return top["score"], top["page"]


inn = []
for q in IN_SCOPE:
    s, p = check(q)
    inn.append(s)
    print(f"IN   {s:.3f}  (p.{p})  {q}")

off = []
for q in OFF_TOPIC:
    s, p = check(q)
    off.append(s)
    print(f"OFF  {s:.3f}  (p.{p})  {q}")

lo, hi = max(off), min(inn)
if lo < hi:
    print(f"\nSuggested SCORE_THRESHOLD ~ {(lo + hi) / 2:.2f}  (off-topic max {lo:.3f}, in-scope min {hi:.3f})")
else:
    print(f"\nScores overlap (off-topic max {lo:.3f} >= in-scope min {hi:.3f}). Edit the questions or add more chapters.")