"""K12 Course Review System - FastAPI Backend."""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)

import asyncio
import base64
import json
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query, Depends, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
from database import SessionLocal, init_db, Subject, Chapter, Tag, Question, AIContent, Student, Attempt, question_tags
from sqlalchemy import func, cast, Date


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

class QuestionUpdate(BaseModel):
    chapter_id: Optional[int] = None
    source: Optional[str] = None
    question_type: Optional[str] = None
    difficulty: Optional[int] = None
    content: Optional[str] = None
    options: Optional[list[str]] = None
    answer: Optional[str] = None
    explanation: Optional[str] = None
    image_url: Optional[str] = None
    tag_names: Optional[list[str]] = None

class SubjectCreate(BaseModel):
    name: str
    level: str  # junior / senior

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


@app.post("/api/seed")
def seed_sample_data(db=Depends(get_db)):
    """One-click seed sample questions."""
    if db.query(Question).count() > 0:
        return {"msg": "Already seeded", "count": db.query(Question).count()}

    math = db.query(Subject).filter(Subject.name == "數學A", Subject.level == "senior").first()
    if not math:
        return {"msg": "Subject not found"}

    chapters_data = [
        "第一章 數與式", "第二章 多項式", "第三章 指數與對數",
        "第四章 三角函數", "第五章 排列組合", "第六章 機率與統計",
        "第七章 向量",
    ]
    chapters = {}
    for i, name in enumerate(chapters_data):
        ch = db.query(Chapter).filter(Chapter.name == name, Chapter.subject_id == math.id).first()
        if not ch:
            ch = Chapter(subject_id=math.id, name=name, sort_order=i + 1)
            db.add(ch)
            db.flush()
        chapters[name] = ch

    samples = [
        {"ch": "第四章 三角函數", "src": "113學測", "content": "若 sin θ = 3/5，且 θ 為第二象限角，則 cos θ 之值為何？", "opts": ["A. 4/5", "B. -4/5", "C. 3/4", "D. -3/4"], "ans": "B", "exp": "由 sin²θ + cos²θ = 1，得 cos²θ = 1 - 9/25 = 16/25，cos θ = ±4/5。因 θ 在第二象限，cos θ < 0，故 cos θ = -4/5。", "diff": 2, "tags": ["三角函數", "畢氏定理"]},
        {"ch": "第五章 排列組合", "src": "113學測", "content": "將 MATH 四個字母全部排成一列，共有幾種排法？", "opts": ["A. 12", "B. 24", "C. 48", "D. 6"], "ans": "B", "exp": "4個相異字母的排列數 = 4! = 4 × 3 × 2 × 1 = 24", "diff": 1, "tags": ["排列", "階乘"]},
        {"ch": "第三章 指數與對數", "src": "112學測", "content": "若 log₂x = 3，則 x 之值為何？", "opts": ["A. 6", "B. 8", "C. 9", "D. 12"], "ans": "B", "exp": "log₂x = 3 表示 2³ = x，故 x = 8。", "diff": 1, "tags": ["對數", "指數"]},
        {"ch": "第六章 機率與統計", "src": "112學測", "content": "擲一公正骰子兩次，兩次點數和為 7 的機率為何？", "opts": ["A. 1/6", "B. 5/36", "C. 1/12", "D. 7/36"], "ans": "A", "exp": "總共 36 種等機率結果。和為 7 的組合：(1,6)(2,5)(3,4)(4,3)(5,2)(6,1) 共 6 種。機率 = 6/36 = 1/6。", "diff": 2, "tags": ["機率", "古典機率"]},
        {"ch": "第一章 數與式", "src": "113學測", "content": "設 a, b 為實數，若 |a - 3| + |b + 2| = 0，則 a + b = ？", "opts": ["A. 1", "B. -1", "C. 5", "D. -5"], "ans": "A", "exp": "因為絕對值 ≥ 0，兩個非負數之和為 0，必須兩者都為 0。故 a - 3 = 0 且 b + 2 = 0，得 a = 3, b = -2，a + b = 1。", "diff": 2, "tags": ["絕對值", "實數"]},
        {"ch": "第二章 多項式", "src": "111學測", "content": "多項式 f(x) = x³ - 2x² - 5x + 6 的一個根為 x = 1，則 f(x) 可分解為？", "opts": ["A. (x-1)(x+2)(x-3)", "B. (x-1)(x-2)(x+3)", "C. (x+1)(x-2)(x-3)", "D. (x-1)(x-2)(x-3)"], "ans": "A", "exp": "f(1) = 1 - 2 - 5 + 6 = 0 確認。以 (x-1) 做綜合除法得 x² - x - 6 = (x+2)(x-3)。故 f(x) = (x-1)(x+2)(x-3)。", "diff": 3, "tags": ["多項式", "因式分解", "綜合除法"]},
        {"ch": "第七章 向量", "src": "112學測", "content": "若向量 a = (2, 3)，b = (1, -1)，則 a · b = ？", "opts": ["A. -1", "B. 1", "C. 5", "D. -5"], "ans": "A", "exp": "a · b = 2×1 + 3×(-1) = 2 - 3 = -1", "diff": 1, "tags": ["向量", "內積"]},
        {"ch": "第四章 三角函數", "src": "111學測", "content": "在△ABC中，若 A = 60°, b = 4, c = 5，則 a = ？", "opts": ["A. √21", "B. √41", "C. √61", "D. √81"], "ans": "A", "exp": "由餘弦定理 a² = b² + c² - 2bc·cos A = 16 + 25 - 2(4)(5)(1/2) = 41 - 20 = 21，故 a = √21。", "diff": 3, "tags": ["三角函數", "餘弦定理"]},
    ]

    count = 0
    for s in samples:
        q = Question(
            chapter_id=chapters[s["ch"]].id, source=s["src"], question_type="single_choice",
            difficulty=s["diff"], content=s["content"],
            options=json.dumps(s["opts"], ensure_ascii=False), answer=s["ans"], explanation=s["exp"],
        )
        for tag_name in s["tags"]:
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
                db.flush()
            q.tags.append(tag)
        db.add(q)
        count += 1
    db.commit()
    return {"msg": "Seeded", "count": count}


@app.get("/api/debug")
def debug_env():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "key_set": bool(key),
        "key_prefix": key[:12] + "..." if len(key) > 12 else "(empty)",
    }


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

    try:
        if req.content_type == "story":
            content = generate_story(q.content, q.answer, q.explanation or "")
        elif req.content_type == "diagram":
            content = generate_diagram(q.content, q.answer)
        elif req.content_type == "hint":
            content = generate_hint(q.content)
            return {"hint": content}
        elif req.content_type == "similar":
            result = generate_similar_question(q.content, q.answer)
            return {"similar_question": result}
        else:
            raise HTTPException(400, f"Unknown content_type: {req.content_type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"AI generation failed: {type(e).__name__}: {e}")

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


# ── Question Update & Delete ──────────────────────────────────────

@app.put("/api/questions/{question_id}")
def update_question(question_id: int, data: QuestionUpdate, db=Depends(get_db)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")

    if data.content is not None:
        q.content = data.content
    if data.answer is not None:
        q.answer = data.answer
    if data.explanation is not None:
        q.explanation = data.explanation
    if data.chapter_id is not None:
        q.chapter_id = data.chapter_id
    if data.source is not None:
        q.source = data.source
    if data.question_type is not None:
        q.question_type = data.question_type
    if data.difficulty is not None:
        q.difficulty = data.difficulty
    if data.image_url is not None:
        q.image_url = data.image_url
    if data.options is not None:
        q.options = json.dumps(data.options, ensure_ascii=False)
    if data.tag_names is not None:
        q.tags.clear()
        for tag_name in data.tag_names:
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
                db.flush()
            q.tags.append(tag)

    db.commit()
    return {"id": q.id, "msg": "Updated"}


@app.delete("/api/questions/{question_id}")
def delete_question(question_id: int, db=Depends(get_db)):
    q = db.query(Question).filter(Question.id == question_id).first()
    if not q:
        raise HTTPException(404, "Question not found")
    # Delete related AI contents and attempts
    db.query(AIContent).filter(AIContent.question_id == question_id).delete()
    db.query(Attempt).filter(Attempt.question_id == question_id).delete()
    q.tags.clear()
    db.delete(q)
    db.commit()
    return {"msg": "Deleted"}


# ── Subject Management ────────────────────────────────────────────

@app.post("/api/subjects")
def create_subject(data: SubjectCreate, db=Depends(get_db)):
    existing = db.query(Subject).filter(
        Subject.name == data.name, Subject.level == data.level
    ).first()
    if existing:
        raise HTTPException(400, f"Subject '{data.name}' ({data.level}) already exists")
    s = Subject(name=data.name, level=data.level)
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name, "level": s.level}


# ── Tags ──────────────────────────────────────────────────────────

@app.get("/api/tags")
def list_tags(db=Depends(get_db)):
    tags = db.query(
        Tag.id, Tag.name, func.count(question_tags.c.question_id).label("count")
    ).outerjoin(question_tags).group_by(Tag.id).order_by(func.count(question_tags.c.question_id).desc()).all()
    return [{"id": t.id, "name": t.name, "count": t.count} for t in tags]


@app.delete("/api/tags/{tag_id}")
def delete_tag(tag_id: int, db=Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(404, "Tag not found")
    tag.questions.clear()
    db.delete(tag)
    db.commit()
    return {"msg": "Deleted"}


# ── Students ──────────────────────────────────────────────────────

@app.get("/api/students")
def list_students(db=Depends(get_db)):
    students = db.query(Student).order_by(Student.id).all()
    return [
        {
            "id": s.id, "name": s.name, "grade": s.grade,
            "email": s.email, "total_attempts": len(s.attempts),
        }
        for s in students
    ]


@app.get("/api/students/{student_id}")
def get_student(student_id: int, db=Depends(get_db)):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        raise HTTPException(404, "Student not found")
    total = len(s.attempts)
    correct = sum(1 for a in s.attempts if a.is_correct)
    return {
        "id": s.id, "name": s.name, "grade": s.grade, "email": s.email,
        "total_attempts": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
    }


@app.put("/api/students/{student_id}")
def update_student(student_id: int, data: StudentCreate, db=Depends(get_db)):
    s = db.query(Student).filter(Student.id == student_id).first()
    if not s:
        raise HTTPException(404, "Student not found")
    s.name = data.name
    s.grade = data.grade
    s.email = data.email
    db.commit()
    return {"id": s.id, "name": s.name}


# ── Attempt History & Trends ──────────────────────────────────────

@app.get("/api/students/{student_id}/attempts")
def list_attempts(
    student_id: int,
    subject_id: Optional[int] = None,
    page: int = 1,
    size: int = 20,
    db=Depends(get_db),
):
    q = db.query(Attempt).filter(Attempt.student_id == student_id)
    if subject_id:
        q = q.join(Question).join(Chapter).filter(Chapter.subject_id == subject_id)
    total = q.count()
    attempts = q.order_by(Attempt.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "total": total,
        "page": page,
        "data": [
            {
                "id": a.id,
                "question_id": a.question_id,
                "question_content": a.question.content[:80],
                "answer_given": a.answer_given,
                "correct_answer": a.question.answer,
                "is_correct": a.is_correct,
                "time_spent": a.time_spent,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attempts
        ],
    }


@app.get("/api/students/{student_id}/trend")
def student_trend(student_id: int, days: int = 14, db=Depends(get_db)):
    """Daily accuracy trend for recent N days."""
    since = datetime.now() - timedelta(days=days)
    attempts = (
        db.query(Attempt)
        .filter(Attempt.student_id == student_id, Attempt.created_at >= since)
        .all()
    )
    daily = {}
    for a in attempts:
        day = a.created_at.strftime("%Y-%m-%d") if a.created_at else "unknown"
        if day not in daily:
            daily[day] = {"total": 0, "correct": 0}
        daily[day]["total"] += 1
        if a.is_correct:
            daily[day]["correct"] += 1

    return [
        {
            "date": d,
            "total": v["total"],
            "correct": v["correct"],
            "accuracy": round(v["correct"] / v["total"] * 100, 1),
        }
        for d, v in sorted(daily.items())
    ]


# ── Smart Practice (弱點優先) ─────────────────────────────────────

@app.get("/api/practice/start")
def start_practice(
    student_id: int,
    subject_id: Optional[int] = None,
    count: int = 10,
    mode: str = "smart",  # smart / random / weak
    db=Depends(get_db),
):
    """Generate a practice set. Modes:
    - smart: mix of weak areas (60%) + random (40%)
    - random: purely random
    - weak: only questions from weak tags
    """
    base_q = db.query(Question)
    if subject_id:
        base_q = base_q.join(Chapter).filter(Chapter.subject_id == subject_id)
    all_questions = base_q.all()

    if not all_questions:
        return {"questions": [], "msg": "No questions available"}

    if mode == "random":
        selected = random.sample(all_questions, min(count, len(all_questions)))
    else:
        # Find weak tags for this student
        attempts = db.query(Attempt).filter(Attempt.student_id == student_id).all()
        tag_stats = {}
        for att in attempts:
            for tag in att.question.tags:
                if tag.name not in tag_stats:
                    tag_stats[tag.name] = {"total": 0, "correct": 0}
                tag_stats[tag.name]["total"] += 1
                if att.is_correct:
                    tag_stats[tag.name]["correct"] += 1

        weak_tag_names = [
            k for k, v in tag_stats.items()
            if v["total"] >= 2 and v["correct"] / v["total"] < 0.7
        ]

        # Split into weak and other pools
        weak_pool = [q for q in all_questions if any(t.name in weak_tag_names for t in q.tags)]
        other_pool = [q for q in all_questions if q not in weak_pool]

        # Also deprioritize recently-correct questions
        recent_correct_ids = {
            a.question_id for a in attempts[-50:]
            if a.is_correct
        }
        other_pool = sorted(other_pool, key=lambda q: q.id in recent_correct_ids)

        if mode == "weak":
            pool = weak_pool if weak_pool else all_questions
            selected = random.sample(pool, min(count, len(pool)))
        else:  # smart
            weak_count = int(count * 0.6)
            random_count = count - weak_count
            weak_pick = random.sample(weak_pool, min(weak_count, len(weak_pool))) if weak_pool else []
            remaining = random_count + (weak_count - len(weak_pick))
            random_pick = random.sample(other_pool, min(remaining, len(other_pool))) if other_pool else []
            selected = weak_pick + random_pick

    random.shuffle(selected)
    return {
        "count": len(selected),
        "mode": mode,
        "questions": [
            {
                "id": q.id,
                "content": q.content,
                "options": json.loads(q.options) if q.options else None,
                "difficulty": q.difficulty,
                "question_type": q.question_type,
                "tags": [t.name for t in q.tags],
            }
            for q in selected
        ],
    }


# ── Batch Attempts (練習結束批次送出) ─────────────────────────────

class BatchAttemptItem(BaseModel):
    question_id: int
    answer_given: str
    time_spent: Optional[int] = None

class BatchAttemptCreate(BaseModel):
    student_id: int
    attempts: list[BatchAttemptItem]


@app.post("/api/attempts/batch")
def batch_record_attempts(data: BatchAttemptCreate, db=Depends(get_db)):
    """Submit multiple attempts at once (end of practice session)."""
    results = []
    for item in data.attempts:
        q = db.query(Question).filter(Question.id == item.question_id).first()
        if not q:
            continue
        is_correct = item.answer_given.strip().upper() == q.answer.strip().upper()
        att = Attempt(
            student_id=data.student_id,
            question_id=item.question_id,
            answer_given=item.answer_given,
            is_correct=is_correct,
            time_spent=item.time_spent,
        )
        db.add(att)
        results.append({
            "question_id": item.question_id,
            "is_correct": is_correct,
            "correct_answer": q.answer,
        })
    db.commit()
    correct_count = sum(1 for r in results if r["is_correct"])
    return {
        "total": len(results),
        "correct": correct_count,
        "accuracy": round(correct_count / len(results) * 100, 1) if results else 0,
        "results": results,
    }


# ── Chapter Management ────────────────────────────────────────────

@app.put("/api/chapters/{chapter_id}")
def update_chapter(chapter_id: int, data: ChapterCreate, db=Depends(get_db)):
    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")
    ch.subject_id = data.subject_id
    ch.name = data.name
    ch.sort_order = data.sort_order
    db.commit()
    return {"id": ch.id, "name": ch.name}


@app.delete("/api/chapters/{chapter_id}")
def delete_chapter(chapter_id: int, db=Depends(get_db)):
    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(404, "Chapter not found")
    q_count = db.query(Question).filter(Question.chapter_id == chapter_id).count()
    if q_count > 0:
        raise HTTPException(400, f"Chapter has {q_count} questions, delete them first")
    db.delete(ch)
    db.commit()
    return {"msg": "Deleted"}


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
