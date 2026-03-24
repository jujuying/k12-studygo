"""AI content generation service using Claude API."""
import os
import json
import asyncio
import edge_tts
from anthropic import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY from env

# Use Haiku for cost efficiency, upgrade to Sonnet for complex subjects
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
ADVANCED_MODEL = "claude-sonnet-4-6-20250514"


def generate_story(question_content: str, answer: str, explanation: str = "") -> str:
    """Turn a question + answer into an easy-to-understand story."""
    prompt = f"""你是一位擅長說故事的台灣國高中老師。
請將以下題目和答案，轉化成一個生動有趣、容易理解的小故事來幫助學生記憶。

要求：
- 用繁體中文
- 故事要貼近台灣學生的生活經驗
- 把關鍵知識點自然融入故事中
- 最後用一句話總結重點
- 300字以內

題目：
{question_content}

正確答案：{answer}
{f"詳解：{explanation}" if explanation else ""}
"""
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def generate_diagram(question_content: str, answer: str, chapter_hint: str = "") -> str:
    """Generate a Mermaid.js diagram for the concept."""
    prompt = f"""你是一位台灣國高中教學視覺化專家。請根據以下題目的核心概念，產生一個 Mermaid.js 圖表。

可用的圖表類型（請選擇最適合的）：
1. flowchart TD — 流程圖：適合因果關係、政治體制架構、決策流程、地理成因
2. mindmap — 心智圖：適合知識點整理、概念分類（如：台灣產業分類、文化特色）
3. timeline — 時間線：適合歷史事件年表、朝代更替、重大事件順序
4. pie — 圓餅圖：適合比例分析（如：產業結構、人口組成、選舉得票）
5. xychart-beta — 長條/折線圖：適合數據比較（如：各國GDP、人口成長、氣溫變化）
6. sequenceDiagram — 序列圖：適合互動過程（如：貿易往來、外交談判、法律程序）
7. graph LR — 關係圖：適合人物關係、國際組織關係、地理區域連結

{f"章節提示：{chapter_hint}" if chapter_hint else ""}

要求：
- 只輸出 mermaid 語法，不要其他說明文字
- 用繁體中文標籤
- 保持簡潔清晰，節點不超過 12 個
- 顏色和樣式盡量豐富（可用 style 或 classDef）
- 確保語法正確，可被 Mermaid.js v11 渲染

題目：
{question_content}

正確答案：{answer}
"""
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    # Extract mermaid code block if wrapped
    if "```mermaid" in text:
        text = text.split("```mermaid")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return text


def generate_hint(question_content: str) -> str:
    """Generate a progressive hint (no direct answer)."""
    prompt = f"""你是一位有耐心的台灣國高中老師。學生正在做以下題目但卡住了。
請給一個循序漸進的提示，引導學生自己找到答案，但不要直接說出答案。

要求：
- 繁體中文
- 先給一個大方向的提示
- 再給一個更具體的思考方向
- 100字以內

題目：
{question_content}
"""
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def generate_similar_question(question_content: str, answer: str) -> dict:
    """Generate a similar practice question."""
    prompt = f"""你是台灣國高中出題老師。請根據以下題目，出一題類似但不同的練習題。

要求：
- 繁體中文
- 測試相同的知識點但情境不同
- 回傳 JSON 格式：{{"content": "題目", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "A", "explanation": "解析"}}
- 只輸出 JSON，不要其他文字

原題：
{question_content}

原答案：{answer}
"""
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


async def generate_audio(text: str, filename: str) -> str:
    """Convert text to speech using edge_tts and save as mp3.

    Args:
        text: The text content to convert to speech.
        filename: The output filename (without directory path).

    Returns:
        Relative path to the generated audio file (e.g. "static/audio/filename.mp3").
    """
    audio_dir = os.path.join(os.path.dirname(__file__), "static", "audio")
    os.makedirs(audio_dir, exist_ok=True)

    output_path = os.path.join(audio_dir, filename)
    voice = "zh-TW-HsiaoChenNeural"

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    return f"static/audio/{filename}"


def extract_question_from_image(image_base64: str) -> dict:
    """Extract question text, options, and answer from a photo of a test question."""
    prompt = """你是一位台灣國高中教育專家，請仔細辨識這張圖片中的考題內容。

請辨識並擷取以下資訊：
1. 題目內容（完整題幹文字）
2. 選項（A/B/C/D，如果有的話）
3. 答案（如果圖片中有標示正確答案）
4. 科目領域（例如：數學、國文、英文、物理、化學、生物、歷史、地理、公民等）
5. 預估難度（1-5，1最簡單，5最難）

請以 JSON 格式回傳，格式如下：
{"content": "題目內容", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "A", "subject_hint": "科目", "difficulty": 3}

注意事項：
- 用繁體中文
- 如果看不清楚某個欄位，該欄位填 null
- options 如果沒有選項則填空陣列 []
- 只輸出 JSON，不要其他文字"""

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )
    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)
