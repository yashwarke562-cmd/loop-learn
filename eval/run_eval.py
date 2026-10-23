"""Accuracy and latency of the diagnosis pipeline on hand-labelled typed samples.

Run from the project root:  python -m eval.run_eval
Uses the real HTTP API through an in-process client, with Gemini switched off, so the numbers cover the
deterministic step checker plus the full request path (auth, validation, storage).
"""
import json
import logging
import os
import statistics
import time
from pathlib import Path

os.environ.setdefault("TEACHER_PIN", "000000")
os.environ.pop("GEMINI_API_KEY", None)
logging.disable(logging.CRITICAL)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


def main() -> None:
    samples = json.loads((Path(__file__).parent / "samples.json").read_text())
    client = TestClient(create_app())
    headers = {"X-Demo-User": "eval_bot", "X-Demo-Role": "student"}
    client.app.state.limiter.limit = 10_000
    hits_mis = hits_step = hits_correct = n_wrong = n_right = 0
    times, misses = [], []
    for s in samples:
        t0 = time.perf_counter()
        r = client.post("/api/diagnose", data={"question": s["q"], "steps": "\n".join(s["steps"])}, headers=headers)
        times.append((time.perf_counter() - t0) * 1000)
        body = r.json()
        if s.get("ok"):
            n_right += 1
            good = body.get("is_correct") is True
            hits_correct += good
        else:
            n_wrong += 1
            got_mis = (body.get("misconception") or {}).get("id")
            got_step = body.get("first_error_step")
            hits_mis += got_mis == s["m"]
            hits_step += got_step == s["step"]
            good = got_mis == s["m"] and got_step == s["step"]
        if not good:
            misses.append({"q": s["q"], "steps": s["steps"], "expected": s.get("m") or "correct",
                           "got": (body.get("misconception") or {}).get("id") or body.get("is_correct")})
    times.sort()
    result = {
        "samples": len(samples),
        "correct_work_recognised": f"{hits_correct}/{n_right}",
        "first_error_step_exact": f"{hits_step}/{n_wrong}",
        "misconception_exact": f"{hits_mis}/{n_wrong}",
        "latency_ms": {"p50": round(statistics.median(times), 1), "p95": round(times[int(len(times) * 0.95) - 1], 1),
                       "max": round(times[-1], 1)},
        "misses": misses,
    }
    print(json.dumps(result, indent=2))
    (Path(__file__).parent / "results.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
