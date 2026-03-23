"""K12 Course Review System - FastAPI Backend."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
from database import SessionLocal, init_db, Subject, Chapter, Tag, Question, AIContent, Student, Attempt, question_tags
from sqlalchemy import func
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="K12 Course Review System", version="0.1.0", lifespan=lifespan)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic Schemas ──────────────────────────────────────────────

class ChapterCreate(BaseModel):
    subject_id: int
    name: str
    sort_order: int = 0

class QuestionCreate(BaseModel):
    chapter_id: Optional[int] = None
    source: Optional[str] = None
    question_type: str = "single_choice"
    difficulty: int = 3
    content: str
    options: Optional[list[str]] = None
    answer: str
    explanation: Optional[str] = None
    image_url: Optional[str] = None
    tag_names: list[str] = []

class QuestionBulkCreate(BaseModel):
    questions: list[QuestionCreate]

class AttemptCreate(BaseModel):
    student_id: int
    question_id: int
    answer_given: str
    time_spent: Optional[int] = None

class StudentCreate(BaseModel):
    name: str
    grade: int
    email: Optional[str] = None

class AIGenerateRequest(BaseModel):
    content_type: str  # story / diagram / hint / similar


# ── Subject & Chapter ─────────────────────────────────────────────

@app.get("/api/subjects")
def list_subjects(level: Optional[str] = None, db=Depends(get_db)):
    q = db.query(Subject)
    if level:
        q = q.filter(Subject.level == level)
    return [{"id": s.id, "name": s.name, "level": s.level} for s in q.all()]


@app.post("/api/chapters")
def create_chapter(data: ChapterCreate, db=Depends(get_db)):
    ch = Chapter(**data.model_dump())
    db.add(ch)
    db.commit()
    return {"id": ch.id, "name": ch.name}


@app.get("/api/chapters")
def list_chapters(subject_id: int, db=Depends(get_db)):
    chapters = db.query(Chapter).filter(Chapter.subject_id == subject_id)\
        .order_by(Chapter.sort_order).all()
    return [{"id": c.id, "name": c.name, "sort_order": c.sort_order} for c in chapters]


# ── Questions ─────────────────────────────────────────────────────

@app.post("/api/questions")
def create_question(data: QuestionCreate, db=Depends(get_db)):
    q = Question(
        chapter_id=data.chapter_id,
        source=data.source,
        question_type=data.question_type,
        difficulty=data.difficulty,
        content=data.content,
        options=json.dumps(data.options, ensure_ascii=False) if data.options else None,
        answer=data.answer,
        explanation=data.explanation,
        image_url=data.image_url,
    )
    # Handle tags
    for tag_name in data.tag_names:
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            db.flush()
        q.tags.append(tag)
    db.add(q)
    db.commit()
    return {"id": q.id}


@app.post("/api/questions/bulk")
def bulk_create_questions(data: QuestionBulkCreate, db=Depends(get_db)):
    ids = []
    for qd in data.questions:
        q = Question(
            chapter_id=qd.chapter_id, source=qd.source,
            question_type=qd.question_type, difficulty=qd.difficulty,
            content=qd.content,
            options=json.dumps(qd.options, ensure_ascii=False) if qd.options else None,
            answer=qd.answer, explanation=qd.explanation, image_url=qd.image_url,
        )
        for tag_name in qd.tag_names:
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
                db.flush()
            q.tags.append(tag)
        db.add(q)
        db.flush()
        ids.append(q.id)
    db.commit()
    return {"count": len(ids), "ids": ids}


@app.get("/api/stats")
def get_stats(db=Depends(get_db)):
    total_questions = db.query(Question).count()
    total_subjects = db.query(Subject).count()
    total_ai = db.query(AIContent).count()
    total_tags = db.query(Tag).count()
    return {
        "total_questions": total_questions,
        "total_subjects": total_subjects,
        "total_ai_contents": total_ai,
        "total_tags": total_tags,
    }


@app.get("/api/questions")
def list_questions(
    chapter_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    source: Optional[str] = None,
    difficulty: Optional[int] = None,
    tag: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    db=Depends(get_db),
):
    q = db.query(Question)
    if chapter_id:
        q = q.filter(Question.chapter_id == chapter_id)
    if subject_id:
        q = q.join(Chapter).filter(Chapter.subject_id == subject_id)
    if source:
        q = q.filter(Question.source.contains(source))
    if difficulty:
        q = q.filter(Question.difficulty == difficulty)
    if tag:
        q = q.join(Question.tags).filter(Tag.name == tag)

    total = q.count()
    questions = q.order_by(Question.id.desc()).offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "data": [
            {
                "id": qq.id,
                "content": qq.content,
                "options": json.loads(qq.options) if qq.options else None,
                "answer": qq.answer,
                "difficulty": qq.difficulty,
                "source": qq.source,
                "question_type": qq.question_type,
                "tags": [t.name for t in qq.tags],
                "has_story": any(c.content_type == "story" for c in qq.ai_contents),
                "has_diagram": any(c.content_type == "diagram" for c in qq.ai_contents),
            }
            for qq in questions
        ],
    }


@app.get("/api/questions/{question_id}")
def get_question(question_id: int, db=Depends(get_db)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    return {
        "id": q.id,
        "content": q.content,
        "options": json.loads(q.options) if q.options else None,
        "answer": q.answer,
        "explanation": q.explanation,
        "difficulty": q.difficulty,
        "source": q.source,
        "question_type": q.question_type,
        "chapter_id": q.chapter_id,
        "image_url": q.image_url,
        "tags": [t.name for t in q.tags],
        "ai_contents": [
            {"id": c.id, "type": c.content_type, "content": c.content}
            for c in q.ai_contents
        ],
    }


# ── AI Content Generation ────────────────────────────────────────

@app.post("/api/questions/{question_id}/generate")
def generate_ai_content(question_id: int, req: AIGenerateRequest, db=Depends(get_db)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")

    from ai_service import generate_story, generate_diagram, generate_hint, generate_similar_question

    if req.content_type == "story":
        content = generate_story(q.content, q.answer, q.explanation or "")
    elif req.content_type == "diagram":
        content = generate_diagram(q.content, q.answer)
    elif req.content_type == "hint":
        content = generate_hint(q.content)
        return {"hint": content}  # hints are not saved
    elif req.content_type == "similar":
        result = generate_similar_question(q.content, q.answer)
        return {"similar_question": result}  # not saved
    else:
        raise HTTPException(400, f"Unknown content_type: {req.content_type}")

    # Save to DB (story / diagram)
    ai = AIContent(
        question_id=question_id,
        content_type=req.content_type,
        content=content,
        model_used="claude-haiku-4-5",
    )
    db.add(ai)
    db.commit()
    return {"id": ai.id, "type": ai.content_type, "content": ai.content}


# ── Students & Attempts ──────────────────────────────────────────

@app.post("/api/students")
def create_student(data: StudentCreate, db=Depends(get_db)):
    s = Student(**data.model_dump())
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name}


@app.post("/api/attempts")
def record_attempt(data: AttemptCreate, db=Depends(get_db)):
    q = db.query(Question).filter(Question.id == data.question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    is_correct = data.answer_given.strip().upper() == q.answer.strip().upper()
    att = Attempt(
        student_id=data.student_id,
        question_id=data.question_id,
        answer_given=data.answer_given,
        is_correct=is_correct,
        time_spent=data.time_spent,
    )
    db.add(att)
    db.commit()
    return {"id": att.id, "is_correct": is_correct, "correct_answer": q.answer}


@app.get("/api/students/{student_id}/stats")
def student_stats(student_id: int, subject_id: Optional[int] = None, db=Depends(get_db)):
    """Get student's accuracy and weak areas."""
    q = db.query(Attempt).filter(Attempt.student_id == student_id)
    if subject_id:
        q = q.join(Question).join(Chapter).filter(Chapter.subject_id == subject_id)

    attempts = q.all()
    if not attempts:
        return {"total": 0, "correct": 0, "accuracy": 0, "weak_tags": []}

    total = len(attempts)
    correct = sum(1 for a in attempts if a.is_correct)

    # Find weak tags (tags with lowest accuracy)
    tag_stats = {}
    for att in attempts:
        question = db.query(Question).get(att.question_id)
        for tag in question.tags:
            if tag.name not in tag_stats:
                tag_stats[tag.name] = {"total": 0, "correct": 0}
            tag_stats[tag.name]["total"] += 1
            if att.is_correct:
                tag_stats[tag.name]["correct"] += 1

    weak_tags = sorted(
        [
            {"tag": k, "accuracy": round(v["correct"] / v["total"] * 100, 1), "count": v["total"]}
            for k, v in tag_stats.items()
            if v["total"] >= 3  # min attempts
        ],
        key=lambda x: x["accuracy"],
    )[:5]

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1),
        "weak_tags": weak_tags,
    }


# ── OCR / Image Question Extraction ──────────────────────────────

class OCRRequest(BaseModel):
    image: str  # base64-encoded image


@app.post("/api/ocr")
def ocr_extract(data: OCRRequest):
    """Extract question data from a base64-encoded image using Claude Vision."""
    from ai_service import extract_question_from_image
    try:
        result = extract_question_from_image(data.image)
        return result
    except Exception as e:
        raise HTTPException(400, f"Failed to extract question from image: {e}")


@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Accept an image file upload, convert to base64, and extract question data."""
    from ai_service import extract_question_from_image

    contents = await file.read()
    image_base64 = base64.b64encode(contents).decode("utf-8")

    try:
        result = extract_question_from_image(image_base64)
        return result
    except Exception as e:
        raise HTTPException(400, f"Failed to extract question from image: {e}")


# ── Audio Generation ──────────────────────────────────────────────

@app.post("/api/questions/{question_id}/audio")
async def generate_question_audio(question_id: int, db=Depends(get_db)):
    """Generate audio narration for a question's story content."""
    from ai_service import generate_story, generate_audio

    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")

    # Check if audio already exists
    existing_audio = next(
        (c for c in q.ai_contents if c.content_type == "audio"), None
    )
    if existing_audio:
        return {"audio_url": f"/{existing_audio.content}"}

    # Check if story exists; if not, generate and save it first
    story_content = next(
        (c for c in q.ai_contents if c.content_type == "story"), None
    )
    if not story_content:
        story_text = generate_story(q.content, q.answer, q.explanation or "")
        story_content = AIContent(
            question_id=question_id,
            content_type="story",
            content=story_text,
            model_used="claude-haiku-4-5",
        )
        db.add(story_content)
        db.commit()
        db.refresh(story_content)

    # Generate audio from the story
    filename = f"question_{question_id}_story.mp3"
    audio_path = await generate_audio(story_content.content, filename)

    # Save audio record to DB
    ai_audio = AIContent(
        question_id=question_id,
        content_type="audio",
        content=audio_path,
        model_used="edge-tts",
    )
    db.add(ai_audio)
    db.commit()

    return {"audio_url": f"/{audio_path}"}


# ── Static Files & Frontend Serving ──────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>K12 Review System</h1><p>Frontend not built yet.</p>")


@app.get("/manifest.json")
def serve_manifest():
    return FileResponse(os.path.join(FRONTEND_DIR, "manifest.json"), media_type="application/manifest+json")


@app.get("/sw.js")
def serve_sw():
    return FileResponse(os.path.join(FRONTEND_DIR, "sw.js"), media_type="application/javascript")


@app.get("/icons/{filename}")
def serve_icon(filename: str):
    icon_path = os.path.join(FRONTEND_DIR, "icons", filename)
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    raise HTTPException(404, "Icon not found")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5050))
    uvicorn.run(app, host="0.0.0.0", port=port)
