"""Seed sample questions for testing the system."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import init_db, SessionLocal, Subject, Chapter, Question, Tag
import json

init_db()
db = SessionLocal()

# Create chapters for senior math
math = db.query(Subject).filter(Subject.name == "數學A", Subject.level == "senior").first()
if not math:
    print("[*] Subject not found")
    sys.exit(1)

chapters_data = [
    "第一章 數與式", "第二章 多項式", "第三章 指數與對數",
    "第四章 三角函數", "第五章 排列組合", "第六章 機率與統計",
    "第七章 向量", "第八章 矩陣", "第九章 圓錐曲線",
]

chapters = {}
for i, name in enumerate(chapters_data):
    ch = db.query(Chapter).filter(Chapter.name == name, Chapter.subject_id == math.id).first()
    if not ch:
        ch = Chapter(subject_id=math.id, name=name, sort_order=i + 1)
        db.add(ch)
        db.flush()
    chapters[name] = ch

# Sample questions
sample_questions = [
    {
        "chapter": "第四章 三角函數",
        "source": "113學測",
        "content": "若 sin θ = 3/5，且 θ 為第二象限角，則 cos θ 之值為何？",
        "options": ["A. 4/5", "B. -4/5", "C. 3/4", "D. -3/4"],
        "answer": "B",
        "explanation": "由 sin²θ + cos²θ = 1，得 cos²θ = 1 - 9/25 = 16/25，cos θ = ±4/5。因 θ 在第二象限，cos θ < 0，故 cos θ = -4/5。",
        "difficulty": 2,
        "tags": ["三角函數", "畢氏定理"],
    },
    {
        "chapter": "第五章 排列組合",
        "source": "113學測",
        "content": "將 MATH 四個字母全部排成一列，共有幾種排法？",
        "options": ["A. 12", "B. 24", "C. 48", "D. 6"],
        "answer": "B",
        "explanation": "4個相異字母的排列數 = 4! = 4 × 3 × 2 × 1 = 24",
        "difficulty": 1,
        "tags": ["排列", "階乘"],
    },
    {
        "chapter": "第三章 指數與對數",
        "source": "112學測",
        "content": "若 log₂x = 3，則 x 之值為何？",
        "options": ["A. 6", "B. 8", "C. 9", "D. 12"],
        "answer": "B",
        "explanation": "log₂x = 3 表示 2³ = x，故 x = 8。",
        "difficulty": 1,
        "tags": ["對數", "指數"],
    },
    {
        "chapter": "第六章 機率與統計",
        "source": "112學測",
        "content": "擲一公正骰子兩次，兩次點數和為 7 的機率為何？",
        "options": ["A. 1/6", "B. 5/36", "C. 1/12", "D. 7/36"],
        "answer": "A",
        "explanation": "總共 36 種等機率結果。和為 7 的組合：(1,6)(2,5)(3,4)(4,3)(5,2)(6,1) 共 6 種。機率 = 6/36 = 1/6。",
        "difficulty": 2,
        "tags": ["機率", "古典機率"],
    },
    {
        "chapter": "第一章 數與式",
        "source": "113學測",
        "content": "設 a, b 為實數，若 |a - 3| + |b + 2| = 0，則 a + b = ？",
        "options": ["A. 1", "B. -1", "C. 5", "D. -5"],
        "answer": "A",
        "explanation": "因為絕對值 ≥ 0，兩個非負數之和為 0，必須兩者都為 0。故 a - 3 = 0 且 b + 2 = 0，得 a = 3, b = -2，a + b = 1。",
        "difficulty": 2,
        "tags": ["絕對值", "實數"],
    },
    {
        "chapter": "第二章 多項式",
        "source": "111學測",
        "content": "多項式 f(x) = x³ - 2x² - 5x + 6 的一個根為 x = 1，則 f(x) 可分解為？",
        "options": [
            "A. (x-1)(x+2)(x-3)",
            "B. (x-1)(x-2)(x+3)",
            "C. (x+1)(x-2)(x-3)",
            "D. (x-1)(x-2)(x-3)"
        ],
        "answer": "A",
        "explanation": "f(1) = 1 - 2 - 5 + 6 = 0 確認。以 (x-1) 做綜合除法得 x² - x - 6 = (x+2)(x-3)。故 f(x) = (x-1)(x+2)(x-3)。",
        "difficulty": 3,
        "tags": ["多項式", "因式分解", "綜合除法"],
    },
    {
        "chapter": "第七章 向量",
        "source": "112學測",
        "content": "若向量 a = (2, 3)，b = (1, -1)，則 a · b = ？",
        "options": ["A. -1", "B. 1", "C. 5", "D. -5"],
        "answer": "A",
        "explanation": "a · b = 2×1 + 3×(-1) = 2 - 3 = -1",
        "difficulty": 1,
        "tags": ["向量", "內積"],
    },
    {
        "chapter": "第四章 三角函數",
        "source": "111學測",
        "content": "在△ABC中，若 A = 60°, b = 4, c = 5，則 a = ？",
        "options": ["A. √21", "B. √41", "C. √61", "D. √81"],
        "answer": "A",
        "explanation": "由餘弦定理 a² = b² + c² - 2bc·cos A = 16 + 25 - 2(4)(5)(1/2) = 41 - 20 = 21，故 a = √21。",
        "difficulty": 3,
        "tags": ["三角函數", "餘弦定理"],
    },
]

count = 0
for qd in sample_questions:
    # Check if already exists
    exists = db.query(Question).filter(
        Question.content == qd["content"]
    ).first()
    if exists:
        continue

    q = Question(
        chapter_id=chapters[qd["chapter"]].id,
        source=qd["source"],
        question_type="single_choice",
        difficulty=qd["difficulty"],
        content=qd["content"],
        options=json.dumps(qd["options"], ensure_ascii=False),
        answer=qd["answer"],
        explanation=qd["explanation"],
    )
    for tag_name in qd["tags"]:
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            db.flush()
        q.tags.append(tag)
    db.add(q)
    count += 1

db.commit()
db.close()
print(f"[*] Seeded {count} sample questions.")
