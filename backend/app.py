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


# ---------------------------------------------------------------------------
# Chinese Language Curriculum: chapters + sample questions (108課綱 國中國文)
# ---------------------------------------------------------------------------
CHINESE_CHAPTERS = {
    # ── 七上 ──
    "七上文言文": [
        "論語選（學而時習之、吾日三省吾身、三人行）",
        "兒時記趣（沈復）",
        "神話與寓言選（夸父逐日、濫竽充數）",
    ],
    "七上白話文": [
        "夏夜（楊喚）與現代詩賞析",
        "背影（朱自清）",
        "紙船印象（洪醒夫）",
    ],
    "七上語文常識": [
        "標點符號使用法",
        "閱讀策略與資訊檢索",
    ],
    # ── 七下 ──
    "七下文言文": [
        "近體詩選（絕句與律詩：登鸛雀樓、山居秋暝、聞官軍收河南河北）",
        "五柳先生傳（陶淵明）",
        "記承天夜遊（蘇軾）",
    ],
    "七下白話文": [
        "謝天（陳之藩）",
        "聲音鐘（陳黎）與新詩選",
        "石虎是我們的龍貓——議題文本",
    ],
    "七下語文常識": [
        "漢字的結構——六書（象形、指事、會意、形聲、轉注、假借）",
        "漢字的流變與書法欣賞",
    ],
    # ── 八上 ──
    "八上文言文": [
        "古體詩選（迢迢牽牛星、慈烏夜啼）",
        "愛蓮說（周敦頤）",
        "張釋之執法（司馬遷）",
        "世說新語選（劉義慶）",
    ],
    "八上白話文": [
        "田園之秋選（陳冠學）",
        "鳥（梁實秋）",
        "下雨天，真好（琦君）",
    ],
    "八上語文常識": [
        "語法（上）——詞類（名詞、動詞、形容詞、副詞、介詞、連接詞）",
        "語法（下）——句型（直述句、倒裝句、被動句、因果句）",
    ],
    # ── 八下 ──
    "八下文言文": [
        "木蘭詩（樂府詩）",
        "陋室銘（劉禹錫）",
        "空城計（羅貫中・三國演義選）",
    ],
    "八下白話文": [
        "我所知道的康橋（徐志摩）",
        "運動家的風度（羅家倫）",
        "科幻極短篇選",
    ],
    "八下語文常識": [
        "應用文——書信與便條",
        "應用文——題辭與柬帖",
    ],
    # ── 九上 ──
    "九上文言文": [
        "詞選（南鄉子 登京口北固亭有懷・辛棄疾）",
        "與宋元思書（吳均）",
        "孟子選——生於憂患死於安樂",
        "大明湖（劉鶚・老殘遊記）",
    ],
    "九上白話文": [
        "蘇東坡突圍（余秋雨）",
        "現代散文與報導文學選讀",
    ],
    "九上語文常識": [
        "應用文——對聯（春聯、輓聯、賀聯）",
    ],
    # ── 九下 ──
    "九下文言文": [
        "元曲選（天淨沙 秋思・馬致遠／沉醉東風 漁父詞）",
        "鄒忌諷齊王納諫（戰國策）",
        "湖心亭看雪（張岱）",
    ],
    "九下白話文": [
        "翻譯文學選讀（羅密歐與茱麗葉、項鍊）",
        "現代小說與議論文選讀",
    ],
    # ── 跨冊主題 ──
    "修辭與寫作": [
        "修辭技巧（譬喻、轉化、映襯、借代、雙關、設問、摹寫、誇飾、排比）",
        "寫作技巧（記敘文、抒情文、說明文、議論文）",
    ],
    "字音字形與成語": [
        "常見易混淆字音字形辨正",
        "成語、慣用語與歇後語",
    ],
    "閱讀素養": [
        "閱讀理解（擷取資訊、統整解釋、省思評鑑）",
        "跨文本比較與圖表判讀",
    ],
    "韻文流變": [
        "韻文發展：古詩→近體詩→詞→曲",
    ],
}

CHINESE_SAMPLE_QUESTIONS = [
    # 文言文
    {"ch": "論語選（學而時習之、吾日三省吾身、三人行）", "src": "113會考", "content": "子曰：「三人行，必有我師焉。擇其善者而從之，其不善者而改之。」下列敘述何者最符合本文主旨？", "opts": ["A. 朋友之間應互相學習", "B. 任何人都有值得學習或警惕之處", "C. 行走時要注意周遭環境", "D. 三個人一起做事比較有效率"], "ans": "B", "exp": "孔子認為與人相處時，對方的優點可以學習，缺點可以作為自我警惕的借鏡。重點不在人數，而在於隨時隨地都能從他人身上獲得啟發。", "diff": 1, "tags": ["論語", "文言文閱讀"]},
    {"ch": "愛蓮說（周敦頤）", "src": "112會考", "content": "「予獨愛蓮之出淤泥而不染，濯清漣而不妖。」作者以蓮花象徵什麼品格？", "opts": ["A. 富貴華麗", "B. 隱逸清高", "C. 廉潔正直，不受環境污染", "D. 追求功名利祿"], "ans": "C", "exp": "周敦頤以蓮花「出淤泥而不染」比喻君子身處污濁環境仍能保持廉潔正直的品格。文中菊花象徵隱逸（陶淵明），牡丹象徵富貴，蓮花象徵君子。", "diff": 2, "tags": ["愛蓮說", "文言文", "修辭"]},
    {"ch": "木蘭詩（樂府詩）", "src": "113會考", "content": "「雄兔腳撲朔，雌兔眼迷離；雙兔傍地走，安能辨我是雄雌？」這段話主要表達什麼意思？", "opts": ["A. 兔子雌雄難以分辨", "B. 木蘭女扮男裝多年無人識破", "C. 戰場上人人平等", "D. 動物的生態特徵"], "ans": "B", "exp": "這是木蘭詩的結尾，以雄兔雌兔奔跑時難以分辨為比喻，暗指木蘭代父從軍十二年，與同袍並肩作戰，竟無人發現她是女子，展現巧妙的譬喻手法。", "diff": 2, "tags": ["木蘭詩", "樂府詩", "譬喻"]},
    {"ch": "孟子選——生於憂患死於安樂", "src": "112會考", "content": "孟子認為上天要將大任交付給一個人之前，必先怎樣磨練他？下列何者不屬於孟子所說的磨練？", "opts": ["A. 苦其心志，勞其筋骨", "B. 餓其體膚，空乏其身", "C. 賜其財富，安其居所", "D. 行拂亂其所為"], "ans": "C", "exp": "孟子認為天降大任者必先經歷心志之苦、筋骨之勞、飢餓貧困等磨練，目的在「動心忍性，增益其所不能」。選項 C 的賜予財富安逸恰好相反。", "diff": 2, "tags": ["孟子", "文言文"]},
    # 白話文
    {"ch": "背影（朱自清）", "src": "113會考", "content": "朱自清〈背影〉中，作者幾度落淚的原因主要與下列何者有關？", "opts": ["A. 對父親年老的不捨與感恩", "B. 對未來前途的擔憂", "C. 對故鄉的思念", "D. 被老師責罵後的委屈"], "ans": "A", "exp": "〈背影〉是朱自清的經典散文，文中作者看到父親費力爬過月台為他買橘子的背影而流淚，表達對父親漸老卻仍為子操勞的感動與不捨，是中國現代文學中最經典的親情描寫之一。", "diff": 1, "tags": ["背影", "白話文", "記敘文"]},
    {"ch": "謝天（陳之藩）", "src": "112會考", "content": "陳之藩〈謝天〉一文中，作者認為「要感謝的人太多了，就感謝天吧」，這句話最主要的含意是？", "opts": ["A. 人應信仰宗教", "B. 天氣影響人的生活甚鉅", "C. 個人的成就來自眾人的幫助，應心存感恩", "D. 人無法控制自己的命運"], "ans": "C", "exp": "陳之藩以自身求學經驗說明，個人成就並非全靠自己，而是得到無數人的幫助。「謝天」不是宗教意涵，而是因為要感謝的人太多，以「天」代表所有幫助過自己的人。", "diff": 2, "tags": ["謝天", "白話文", "議論文"]},
    # 語文常識
    {"ch": "漢字的結構——六書（象形、指事、會意、形聲、轉注、假借）", "src": "113會考", "content": "下列哪一個字屬於「會意」字？", "opts": ["A. 山（象形）", "B. 上（指事）", "C. 休（會意）", "D. 河（形聲）"], "ans": "C", "exp": "「休」字由「人」靠著「木」組成，會合兩個字的意義來表達「休息」的概念，屬於會意字。象形是描摹事物形狀（山），指事是在符號上加指示標記（上），形聲是一部分表音一部分表義（河）。", "diff": 2, "tags": ["六書", "語文常識"]},
    {"ch": "語法（上）——詞類（名詞、動詞、形容詞、副詞、介詞、連接詞）", "src": "112會考", "content": "「她『靜靜地』坐在窗邊看書。」句中「靜靜地」屬於下列哪一種詞類？", "opts": ["A. 名詞", "B. 形容詞", "C. 副詞", "D. 介詞"], "ans": "C", "exp": "「靜靜地」修飾動詞「坐」，說明動作的狀態，屬於副詞。形容詞修飾名詞（如「靜靜的房間」），副詞則修飾動詞、形容詞或其他副詞。", "diff": 2, "tags": ["詞類", "語法"]},
    # 修辭
    {"ch": "修辭技巧（譬喻、轉化、映襯、借代、雙關、設問、摹寫、誇飾、排比）", "src": "113會考", "content": "「他的笑容像春風一樣溫暖。」這句話使用了哪一種修辭技巧？", "opts": ["A. 轉化", "B. 譬喻", "C. 誇飾", "D. 映襯"], "ans": "B", "exp": "以「春風」比喻「笑容的溫暖」，具備喻體（笑容）、喻詞（像）、喻依（春風），屬於明喻（譬喻的一種）。轉化是將物擬人或人擬物，誇飾是言過其實，映襯是對比。", "diff": 1, "tags": ["修辭", "譬喻"]},
    # 閱讀素養
    {"ch": "閱讀理解（擷取資訊、統整解釋、省思評鑑）", "src": "113會考", "content": "閱讀以下短文：「根據統計，台灣每年丟棄的食物量約375萬噸，足以堆滿13座台北101大樓。其中家庭廚餘占最大宗，其次是餐飲業。」下列何者是本段文字的主要訊息？", "opts": ["A. 台北101大樓的高度", "B. 台灣食物浪費問題嚴重", "C. 餐飲業應負最大責任", "D. 台灣人不懂得珍惜食物的原因"], "ans": "B", "exp": "本段以數據（375萬噸、13座101）凸顯台灣食物浪費的嚴重程度，這是主要訊息。C 錯在「最大宗」是家庭廚餘非餐飲業；D 文中未提及原因。此題考驗「擷取資訊」與「統整解釋」的閱讀能力。", "diff": 2, "tags": ["閱讀理解", "素養題"]},
    {"ch": "成語、慣用語與歇後語", "src": "112會考", "content": "下列成語使用，何者最為恰當？", "opts": ["A. 他做事總是虎頭蛇尾，令人讚賞", "B. 這場演出真是乏善可陳，觀眾掌聲如雷", "C. 小明杯水車薪的努力，終於完成了整個專案", "D. 老師諄諄教誨，我們應心存感激"], "ans": "D", "exp": "「諄諄教誨」指老師懇切地教導，用於表達感恩恰當。A「虎頭蛇尾」是負面詞不配「讚賞」；B「乏善可陳」指沒什麼好說的，與掌聲如雷矛盾；C「杯水車薪」指力量太小無法解決問題，與「終於完成」矛盾。", "diff": 2, "tags": ["成語", "語文常識"]},
]


# ---------------------------------------------------------------------------
# Social Studies Curriculum: chapters + sample questions (108課綱 國中社會)
# ---------------------------------------------------------------------------
SOCIAL_CHAPTERS = {
    # ── 歷史 ──
    "七上歷史": [
        "史前台灣與原住民族文化",
        "大航海時代的台灣（荷西時期）",
        "鄭氏時期的經營",
        "清帝國時期的台灣",
    ],
    "七下歷史": [
        "清末開港與近代化建設",
        "日治時期的殖民統治與社會變遷",
        "戰後台灣的政治與經濟發展",
    ],
    "八上歷史": [
        "商周至隋唐的國家與社會",
        "宋元多民族並立與交流",
        "東亞文化圈的形成與互動",
    ],
    "八下歷史": [
        "明清時期東亞世界的變動",
        "晚清的變局與改革",
        "中華民國的建立與發展",
    ],
    "九上歷史": [
        "古代文明的發展",
        "中世紀歐洲與伊斯蘭世界",
        "文藝復興與宗教改革",
        "大航海與近代世界的形成",
    ],
    "九下歷史": [
        "啟蒙運動與美法革命",
        "工業革命與帝國主義",
        "兩次世界大戰與冷戰",
        "當代世界的發展與挑戰",
    ],
    # ── 地理 ──
    "七上地理": [
        "地理學基本概念與地圖技能",
        "台灣的位置與地形",
        "台灣的氣候與水文",
    ],
    "七下地理": [
        "台灣的人口與族群",
        "台灣的產業發展",
        "台灣的聚落、交通與區域特色",
    ],
    "八上地理": [
        "中國的自然環境",
        "中國的人口與產業",
        "中國的區域劃分",
    ],
    "八下地理": [
        "東南亞與南亞",
        "西亞、北非與東北亞",
    ],
    "九上地理": [
        "歐洲的自然與人文環境",
        "俄羅斯、中亞與非洲",
    ],
    "九下地理": [
        "北美洲與中南美洲",
        "大洋洲、兩極與全球議題",
    ],
    # ── 公民與社會 ──
    "七上公民": [
        "自我探索與人際關係",
        "家庭與性別平等",
    ],
    "七下公民": [
        "社會文化與多元",
        "社會規範、法律與公民參與",
    ],
    "八上公民": [
        "國家與民主政治",
        "中央與地方政府",
        "政治參與與選舉",
    ],
    "八下公民": [
        "法律的基本概念（民法與刑法）",
        "權利救濟與少年事件處理",
    ],
    "九上公民": [
        "經濟學基本概念（供需與市場）",
        "生產、消費與貨幣金融",
    ],
    "九下公民": [
        "全球化與國際組織",
        "永續發展、媒體素養與公民責任",
    ],
}

SOCIAL_SAMPLE_QUESTIONS = [
    # 歷史
    {"ch": "史前台灣與原住民族文化", "src": "112會考", "content": "台灣目前發現最早的人類化石為下列何者？", "opts": ["A. 長濱文化人", "B. 左鎮人", "C. 卑南文化人", "D. 澎湖原人"], "ans": "D", "exp": "澎湖原人的下顎骨化石是目前台灣發現年代最久遠的人類化石，距今約 45 萬年至 19 萬年前。", "diff": 2, "tags": ["台灣史前文化", "考古"]},
    {"ch": "大航海時代的台灣（荷西時期）", "src": "113會考", "content": "17 世紀荷蘭東印度公司在台灣的統治中心位於下列何處？", "opts": ["A. 淡水", "B. 基隆", "C. 大員（台南安平）", "D. 鹿港"], "ans": "C", "exp": "荷蘭東印度公司於 1624 年在大員（今台南安平）建立熱蘭遮城，作為統治台灣的行政中心。", "diff": 1, "tags": ["荷蘭時期", "大航海"]},
    {"ch": "日治時期的殖民統治與社會變遷", "src": "112會考", "content": "日治時期推動的「皇民化運動」主要目的為何？", "opts": ["A. 推廣日本文學", "B. 將台灣人同化為日本人", "C. 發展台灣經濟", "D. 促進台日貿易"], "ans": "B", "exp": "皇民化運動始於 1937 年中日戰爭爆發後，目的是將台灣人改造為效忠天皇的日本國民，包括改姓名、廢漢文、推行國語（日語）等措施。", "diff": 2, "tags": ["日治時期", "皇民化"]},
    {"ch": "宋元多民族並立與交流", "src": "113會考", "content": "宋代時，政府為增加財政收入而大力發展的經濟活動為何？", "opts": ["A. 畜牧業", "B. 海外貿易", "C. 礦業開發", "D. 軍事屯田"], "ans": "B", "exp": "宋代因北方領土受遼、金壓迫，積極發展海外貿易，在廣州、泉州、明州等地設置市舶司管理貿易，成為重要財政來源。", "diff": 2, "tags": ["宋代", "海外貿易"]},
    {"ch": "兩次世界大戰與冷戰", "src": "112會考", "content": "冷戰時期，世界被劃分為兩大陣營，其核心對立的兩國為？", "opts": ["A. 英國與法國", "B. 美國與蘇聯", "C. 中國與日本", "D. 德國與義大利"], "ans": "B", "exp": "冷戰（1947-1991）是以美國為首的資本主義陣營與以蘇聯為首的共產主義陣營之間的對抗，雙方在政治、軍事、經濟和意識形態上全面對立。", "diff": 1, "tags": ["冷戰", "世界史"]},
    # 地理
    {"ch": "台灣的位置與地形", "src": "113會考", "content": "台灣本島最高峰為下列何者？", "opts": ["A. 雪山", "B. 玉山", "C. 合歡山", "D. 阿里山"], "ans": "B", "exp": "玉山主峰海拔 3,952 公尺，是台灣也是東亞第一高峰。", "diff": 1, "tags": ["台灣地形", "山脈"]},
    {"ch": "台灣的氣候與水文", "src": "112會考", "content": "台灣北部冬季多雨的主要原因為何？", "opts": ["A. 颱風帶來降雨", "B. 東北季風遇山地形抬升", "C. 太平洋高壓影響", "D. 西南氣流帶來水氣"], "ans": "B", "exp": "冬季東北季風從海面帶來水氣，遇到台灣北部山地產生地形雨，因此北部冬季降雨較多，形成「冬雨型」氣候特徵。", "diff": 2, "tags": ["台灣氣候", "季風"]},
    {"ch": "中國的自然環境", "src": "113會考", "content": "中國地勢呈現何種特徵？", "opts": ["A. 北高南低", "B. 西高東低，三級階梯", "C. 中間高四周低", "D. 東西對稱"], "ans": "B", "exp": "中國地勢西高東低，大致呈三級階梯狀分布：第一階梯為青藏高原（平均 4000 公尺以上），第二階梯為高原盆地（1000-2000 公尺），第三階梯為平原丘陵（500 公尺以下）。", "diff": 2, "tags": ["中國地理", "地形"]},
    {"ch": "北美洲與中南美洲", "src": "112會考", "content": "下列何者為連接大西洋與太平洋的重要人工水道？", "opts": ["A. 蘇乊士運河", "B. 巴拿馬運河", "C. 基爾運河", "D. 京杭大運河"], "ans": "B", "exp": "巴拿馬運河位於中美洲巴拿馬境內，連接大西洋與太平洋，大幅縮短船隻繞行南美洲的航程，是全球最重要的航運水道之一。", "diff": 1, "tags": ["美洲地理", "運河"]},
    # 公民
    {"ch": "國家與民主政治", "src": "113會考", "content": "我國的政府體制中，負責審查國家預算的機關為何？", "opts": ["A. 行政院", "B. 立法院", "C. 監察院", "D. 考試院"], "ans": "B", "exp": "依據《憲法》規定，立法院掌有審議預算案之權，行政院須將年度預算案送交立法院審議通過後始得執行。", "diff": 2, "tags": ["政府體制", "立法院"]},
    {"ch": "法律的基本概念（民法與刑法）", "src": "112會考", "content": "小明在網路上購買商品後想要退貨，依《消費者保護法》規定，他在收到商品後幾天內可以無條件退貨？", "opts": ["A. 3 天", "B. 7 天", "C. 14 天", "D. 30 天"], "ans": "B", "exp": "依《消費者保護法》第 19 條規定，通訊交易（包括網路購物）的消費者在收到商品後 7 日內，得不附理由退回商品。", "diff": 2, "tags": ["消保法", "消費者權益"]},
    {"ch": "經濟學基本概念（供需與市場）", "src": "113會考", "content": "當某商品價格上升時，在其他條件不變下，消費者對該商品的需求量會如何變化？", "opts": ["A. 增加", "B. 減少", "C. 不變", "D. 無法判斷"], "ans": "B", "exp": "根據需求法則，在其他條件不變下，商品價格與需求量呈反向關係——價格上升，需求量下降；價格下降，需求量上升。", "diff": 1, "tags": ["需求法則", "經濟學"]},
]


@app.post("/api/seed-chinese")
def seed_chinese_data(db=Depends(get_db)):
    """Seed 108-curriculum Chinese language chapters and sample questions for junior high."""
    chinese = db.query(Subject).filter(
        Subject.name == "國文", Subject.level == "junior"
    ).first()
    if not chinese:
        return {"msg": "Subject '國文' not found"}

    existing = db.query(Chapter).filter(Chapter.subject_id == chinese.id).count()
    if existing > 0:
        return {"msg": "Chinese already seeded", "chapters": existing}

    chapter_map = {}
    sort_idx = 0
    for group, topics in CHINESE_CHAPTERS.items():
        for topic in topics:
            full_name = f"{group}｜{topic}"
            sort_idx += 1
            ch = Chapter(subject_id=chinese.id, name=full_name, sort_order=sort_idx)
            db.add(ch)
            db.flush()
            chapter_map[topic] = ch

    count = 0
    for s in CHINESE_SAMPLE_QUESTIONS:
        ch = chapter_map.get(s["ch"])
        if not ch:
            continue
        q = Question(
            chapter_id=ch.id, source=s["src"], question_type="single_choice",
            difficulty=s["diff"], content=s["content"],
            options=json.dumps(s["opts"], ensure_ascii=False),
            answer=s["ans"], explanation=s["exp"],
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
    return {"msg": "Chinese seeded", "chapters": sort_idx, "questions": count}


@app.post("/api/seed-social")
def seed_social_data(db=Depends(get_db)):
    """Seed 108-curriculum social studies chapters and sample questions for junior high."""
    social = db.query(Subject).filter(
        Subject.name == "社會", Subject.level == "junior"
    ).first()
    if not social:
        return {"msg": "Subject '社會' not found"}

    # Check if already seeded (by checking if chapters exist)
    existing = db.query(Chapter).filter(Chapter.subject_id == social.id).count()
    if existing > 0:
        return {"msg": "Social studies already seeded", "chapters": existing}

    # Create all chapters
    chapter_map = {}  # topic_name -> Chapter object
    sort_idx = 0
    for group, topics in SOCIAL_CHAPTERS.items():
        for topic in topics:
            full_name = f"{group}｜{topic}"
            sort_idx += 1
            ch = Chapter(subject_id=social.id, name=full_name, sort_order=sort_idx)
            db.add(ch)
            db.flush()
            chapter_map[topic] = ch

    # Create sample questions
    count = 0
    for s in SOCIAL_SAMPLE_QUESTIONS:
        ch = chapter_map.get(s["ch"])
        if not ch:
            continue
        q = Question(
            chapter_id=ch.id, source=s["src"], question_type="single_choice",
            difficulty=s["diff"], content=s["content"],
            options=json.dumps(s["opts"], ensure_ascii=False),
            answer=s["ans"], explanation=s["exp"],
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
    return {
        "msg": "Social studies seeded",
        "chapters": sort_idx,
        "questions": count,
    }


# ---------------------------------------------------------------------------
# AI-powered question generation from curriculum topic
# ---------------------------------------------------------------------------
class GenerateTopicRequest(BaseModel):
    subject_id: int
    chapter_id: int
    topic_description: Optional[str] = None
    count: int = 3
    difficulty: Optional[int] = None  # 1-5, None = mixed


@app.post("/api/generate-topic-questions")
def generate_topic_questions(req: GenerateTopicRequest, db=Depends(get_db)):
    """Use AI to generate questions based on a chapter / curriculum topic."""
    from ai_service import client, DEFAULT_MODEL

    chapter = db.query(Chapter).get(req.chapter_id)
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    subject = db.query(Subject).get(req.subject_id)
    if not subject:
        raise HTTPException(404, "Subject not found")

    topic = req.topic_description or chapter.name
    diff_instruction = (
        f"所有題目難度為 {req.difficulty}（1 最易 5 最難）"
        if req.difficulty
        else "題目難度混合，包含簡單(1-2)、中等(3)、困難(4-5)"
    )

    prompt = f"""你是一位專業的台灣國中社會科出題老師，精通 108 課綱。
請根據以下主題，出 {req.count} 題選擇題。

科目：{subject.name}
章節：{chapter.name}
主題補充：{topic}

要求：
- 繁體中文，符合台灣 108 課綱國中程度
- {diff_instruction}
- 題目要素養導向，融入生活情境或史料判讀，避免純背誦題
- 每題 4 個選項（A/B/C/D）
- 附上詳細解析，說明為何正確及其他選項為何錯誤
- 附上 1-3 個知識點標籤

回傳 JSON 陣列，格式：
[
  {{
    "content": "題幹",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "B",
    "explanation": "詳解",
    "difficulty": 2,
    "tags": ["標籤1", "標籤2"]
  }}
]
只輸出 JSON，不要其他文字。"""

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        questions_data = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(500, "AI returned invalid JSON")

    # Save to database
    created_ids = []
    for qd in questions_data:
        q = Question(
            chapter_id=chapter.id,
            source="AI 自動出題",
            question_type="single_choice",
            difficulty=qd.get("difficulty", 3),
            content=qd["content"],
            options=json.dumps(qd["options"], ensure_ascii=False),
            answer=qd["answer"],
            explanation=qd.get("explanation", ""),
        )
        for tag_name in qd.get("tags", []):
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.add(tag)
                db.flush()
            q.tags.append(tag)
        db.add(q)
        db.flush()
        created_ids.append(q.id)

    db.commit()
    return {"msg": f"Generated {len(created_ids)} questions", "ids": created_ids}


# ---------------------------------------------------------------------------
# AI Random Question — generate 1 question on-the-fly, save to DB, return it
# ---------------------------------------------------------------------------
class AIRandomRequest(BaseModel):
    subject_id: int
    chapter_id: Optional[int] = None
    difficulty: Optional[int] = None  # 1-5, None = random


@app.post("/api/ai-random-question")
def ai_random_question(req: AIRandomRequest, db=Depends(get_db)):
    """Generate a single AI question, persist it, and return for immediate practice."""
    from ai_service import client, DEFAULT_MODEL

    subject = db.query(Subject).get(req.subject_id)
    if not subject:
        raise HTTPException(404, "Subject not found")

    # Pick chapter: specific or random from subject
    if req.chapter_id:
        chapter = db.query(Chapter).get(req.chapter_id)
        if not chapter:
            raise HTTPException(404, "Chapter not found")
    else:
        chapters = db.query(Chapter).filter(Chapter.subject_id == req.subject_id).all()
        if not chapters:
            raise HTTPException(400, "No chapters for this subject")
        chapter = random.choice(chapters)

    diff_instruction = (
        f"難度為 {req.difficulty}（1 最易 5 最難）"
        if req.difficulty
        else f"難度隨機（1-5 之間）"
    )

    prompt = f"""你是一位專業的台灣國高中出題老師，精通 108 課綱。
請出 1 題選擇題。

科目：{subject.name}（{'國中' if subject.level == 'junior' else '高中'}）
章節：{chapter.name}

要求：
- 繁體中文，符合台灣 108 課綱程度
- {diff_instruction}
- 素養導向，融入生活情境、圖表判讀或資料分析，避免純背誦
- 4 個選項（A/B/C/D），只有 1 個正確
- 附詳細解析（為何正確、其他選項為何錯）
- 附 1-3 個知識點標籤
- 每次出題內容要有變化，不要重複

回傳 JSON：
{{"content": "題幹", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "B", "explanation": "詳解", "difficulty": 3, "tags": ["標籤"]}}
只輸出 JSON，不要其他文字。"""

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        qd = json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(500, "AI returned invalid JSON")

    # Save to database
    q = Question(
        chapter_id=chapter.id,
        source="AI 隨機出題",
        question_type="single_choice",
        difficulty=qd.get("difficulty", 3),
        content=qd["content"],
        options=json.dumps(qd["options"], ensure_ascii=False),
        answer=qd["answer"],
        explanation=qd.get("explanation", ""),
    )
    for tag_name in qd.get("tags", []):
        tag = db.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
            db.flush()
        q.tags.append(tag)
    db.add(q)
    db.flush()

    # Auto-generate Mermaid diagram and save as AI content
    diagram_content = None
    try:
        from ai_service import generate_diagram
        diagram_content = generate_diagram(
            qd["content"], qd["answer"], chapter_hint=chapter.name
        )
        ai_diagram = AIContent(
            question_id=q.id,
            content_type="diagram",
            content=diagram_content,
            model_used="claude-haiku-4-5-20251001",
        )
        db.add(ai_diagram)
    except Exception:
        pass  # Diagram generation is optional, don't block the question

    db.commit()

    return {
        "id": q.id,
        "content": qd["content"],
        "options": qd["options"],
        "answer": qd["answer"],
        "explanation": qd.get("explanation", ""),
        "difficulty": qd.get("difficulty", 3),
        "tags": qd.get("tags", []),
        "chapter": chapter.name,
        "subject": subject.name,
        "diagram": diagram_content,
    }


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
            ch_name = q.chapter.name if q.chapter else ""
            content = generate_diagram(q.content, q.answer, chapter_hint=ch_name)
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
