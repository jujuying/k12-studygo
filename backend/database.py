"""Database models and connection for K12 review system."""
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, ForeignKey, Boolean, Table
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "k12.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# Many-to-many: questions <-> knowledge tags
question_tags = Table(
    "question_tags", Base.metadata,
    Column("question_id", Integer, ForeignKey("questions.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Subject(Base):
    """科目 (國文/英文/數學/物理/化學/生物/歷史/地理/公民)"""
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    level = Column(String(10), nullable=False)  # junior / senior
    chapters = relationship("Chapter", back_populates="subject")


class Chapter(Base):
    """章節"""
    __tablename__ = "chapters"
    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    name = Column(String(200), nullable=False)
    sort_order = Column(Integer, default=0)
    subject = relationship("Subject", back_populates="chapters")
    questions = relationship("Question", back_populates="chapter")


class Tag(Base):
    """知識點標籤"""
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    questions = relationship("Question", secondary=question_tags, back_populates="tags")


class Question(Base):
    """題目"""
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"))
    source = Column(String(200))          # e.g. "113學測", "112會考"
    question_type = Column(String(20))    # single_choice / multi_choice / fill / essay
    difficulty = Column(Integer, default=3)  # 1~5
    content = Column(Text, nullable=False)   # 題目本文 (markdown)
    options = Column(Text)                   # JSON: ["A. ...", "B. ...", ...]
    answer = Column(String(200))             # 正確答案
    explanation = Column(Text)               # 原始詳解
    image_url = Column(String(500))          # 題目附圖
    created_at = Column(DateTime, default=datetime.now)

    chapter = relationship("Chapter", back_populates="questions")
    tags = relationship("Tag", secondary=question_tags, back_populates="questions")
    ai_contents = relationship("AIContent", back_populates="question")
    attempts = relationship("Attempt", back_populates="question")


class AIContent(Base):
    """AI 生成的輔助內容"""
    __tablename__ = "ai_contents"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    content_type = Column(String(20), nullable=False)  # story / diagram / audio / video
    content = Column(Text, nullable=False)              # markdown / SVG / file path
    model_used = Column(String(50))                     # claude-haiku-4-5 etc.
    created_at = Column(DateTime, default=datetime.now)

    question = relationship("Question", back_populates="ai_contents")


class Student(Base):
    """學生"""
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    grade = Column(Integer)  # 7~12
    email = Column(String(200))
    created_at = Column(DateTime, default=datetime.now)
    attempts = relationship("Attempt", back_populates="student")


class Attempt(Base):
    """答題紀錄"""
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_given = Column(String(200))
    is_correct = Column(Boolean)
    time_spent = Column(Integer)  # seconds
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student", back_populates="attempts")
    question = relationship("Question", back_populates="attempts")


def init_db():
    """Create all tables and seed default subjects."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    if session.query(Subject).count() == 0:
        subjects = [
            # 國中
            ("國文", "junior"), ("英文", "junior"), ("數學", "junior"),
            ("自然", "junior"), ("社會", "junior"),
            # 高中
            ("國文", "senior"), ("英文", "senior"),
            ("數學A", "senior"), ("數學B", "senior"),
            ("物理", "senior"), ("化學", "senior"), ("生物", "senior"),
            ("歷史", "senior"), ("地理", "senior"), ("公民", "senior"),
        ]
        for name, level in subjects:
            session.add(Subject(name=name, level=level))
        session.commit()
    session.close()


if __name__ == "__main__":
    init_db()
    print("[*] Database initialized.")
