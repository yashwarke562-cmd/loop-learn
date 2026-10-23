"""LearnLoop API: diagnose a student's algebra, adapt practice, and summarise the class for the teacher."""
from __future__ import annotations

import json
import logging
import secrets
import time
from fractions import Fraction
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import practice as practice_agent
from .agents.diagnosis import diagnose
from .agents.gemini import build_llm
from .algebra import AlgebraError, MISCONCEPTIONS, parse_equation, parse_number
from .auth import Principal, get_principal
from .config import Settings
from .security import RateLimiter, SECURITY_HEADERS, pseudonymize, sniff_image
from .store import Store, level_for

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = 6 * 1024 * 1024

logging.basicConfig(level=logging.INFO, format="%(message)s")
audit_log = logging.getLogger("learnloop.audit")


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=4, max_length=40)
    answer: str = Field(min_length=1, max_length=30)


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="LearnLoop", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.store = Store()
    app.state.llm = build_llm(settings)
    app.state.limiter = RateLimiter(settings.rate_per_minute)

    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                           allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "Authorization", "X-Demo-User", "X-Demo-Role", "X-Demo-Pin"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        # Enable browser caching for static stylesheets and scripts while preserving no-store on APIs
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    def audit(p: Principal, action: str, outcome: str, **extra) -> None:
        audit_log.info(json.dumps({"ts": round(time.time()), "user": pseudonymize(p.user_id, settings.id_salt),
                                   "role": p.role, "action": action, "outcome": outcome, **extra}))

    def limited(p: Principal, bucket: str) -> None:
        if not app.state.limiter.allow(f"{p.user_id}:{bucket}"):
            raise HTTPException(429, "Slow down a little and try again in a minute.")

    def student(p: Principal = Depends(get_principal)) -> Principal:
        return p  # teachers may also try the student view

    def teacher(p: Principal = Depends(get_principal)) -> Principal:
        if p.role != "teacher":
            raise HTTPException(403, "Teachers only")
        return p

    def uid_of(p: Principal) -> str:
        return pseudonymize(p.user_id, settings.id_salt)

    # ------------------------------------------------------------------ routes
    @app.get("/api/health")
    def health():
        return {"ok": True, "gemini": app.state.llm is not None, "auth_mode": settings.auth_mode,
                "skills": practice_agent.SKILLS}

    @app.get("/api/me")
    def me(p: Principal = Depends(get_principal)):
        return {"role": p.role}

    @app.post("/api/diagnose")
    async def api_diagnose(question: str = Form(..., max_length=80), steps: str = Form("", max_length=1200),
                           image: UploadFile | None = File(None), p: Principal = Depends(student)):
        limited(p, "diagnose")
        try:
            parse_equation(question)
        except AlgebraError:
            raise HTTPException(422, "The question must be an equation like 2x + 3 = 11.")
        img = None
        if image is not None and image.filename:
            data = await image.read(settings.max_image_bytes + 1)
            if len(data) > settings.max_image_bytes:
                raise HTTPException(413, "Image is too large (max 4 MB).")
            mime = sniff_image(data)
            if mime is None:
                raise HTTPException(415, "Please upload a PNG, JPEG or WebP image.")
            img = (data, mime)
        elif not steps.strip():
            raise HTTPException(422, "Type your steps or upload a photo.")

        result = diagnose(question, steps, img, app.state.llm)
        uid = uid_of(p)
        if result["status"] == "ok":
            skill = result["skill_tag"]
            correct = result["is_correct"]
            app.state.store.update_mastery(uid, skill, correct)
            app.state.store.add_event(uid, "diagnosis", skill,
                                      (result["misconception"] or {}).get("id"), result["needs_teacher"])
        elif result["status"] == "blocked":
            audit(p, "diagnose", "blocked_injection")
        audit(p, "diagnose", result["status"], source=result.get("source", "none"),
              misconception=(result.get("misconception") or {}).get("id"))
        result.pop("prev_line", None)
        return result

    @app.get("/api/practice/next")
    def practice_next(skill: str | None = None, p: Principal = Depends(student)):
        limited(p, "practice")
        uid = uid_of(p)
        store = app.state.store
        if skill is not None and skill not in practice_agent.PRACTICE_SKILLS:
            raise HTTPException(422, "Unknown skill")
        skill = skill or store.weakest_skill(uid, "moving_terms")
        if skill not in practice_agent.PRACTICE_SKILLS:
            skill = "general"
        score = store.get_mastery(uid).get(skill, {"score": 0.3})["score"]
        level = level_for(score)
        question, answer = practice_agent.generate(skill, level)
        qid = secrets.token_urlsafe(8)
        store.put_question(uid, qid, answer, skill)
        return {"question_id": qid, "question": question, "skill": skill, "level": level}

    @app.post("/api/practice/answer")
    def practice_answer(body: AnswerIn, p: Principal = Depends(student)):
        limited(p, "practice")
        uid = uid_of(p)
        pending = app.state.store.pop_question(uid, body.question_id)
        if pending is None:
            raise HTTPException(404, "That question has expired. Ask for a new one.")
        try:
            given = parse_number(body.answer)
        except AlgebraError:
            app.state.store.put_question(uid, body.question_id, pending["answer"], pending["skill"])
            raise HTTPException(422, "Write your answer as a number, like 4 or -3/2.")
        correct = given == Fraction(pending["answer"])
        mastery = app.state.store.update_mastery(uid, pending["skill"], correct)
        app.state.store.add_event(uid, "practice", pending["skill"], None, False)
        audit(p, "practice", "correct" if correct else "wrong", skill=pending["skill"])
        return {"correct": correct, "answer": pending["answer"], "skill": pending["skill"], "mastery": mastery,
                "level": level_for(mastery["score"])}

    @app.get("/api/mastery")
    def mastery(p: Principal = Depends(student)):
        return {"skills": app.state.store.get_mastery(uid_of(p))}

    @app.get("/api/teacher/summary")
    def teacher_summary(p: Principal = Depends(teacher)):
        limited(p, "teacher")
        s = app.state.store.class_summary()
        rows = [{"id": mid, "title": MISCONCEPTIONS[mid][0], "count": n, "tip": MISCONCEPTIONS[mid][1]}
                for mid, n in s["misconceptions"] if mid in MISCONCEPTIONS]
        s["misconceptions"] = rows
        s["mini_lesson"] = (f"Open the next class with 3 quick examples on: {rows[0]['title'].lower()}. "
                            f"Key idea: {rows[0]['tip']}") if rows else None
        audit(p, "teacher_summary", "ok")
        return s

    # ------------------------------------------------------------------ static site
    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if settings.teacher_pin_generated and settings.auth_mode == "demo":
        logging.getLogger("learnloop").warning("Demo teacher PIN for this run: %s", settings.teacher_pin)
    return app


app = create_app()
