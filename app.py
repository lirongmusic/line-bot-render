import os
import requests
import csv
import io
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from openai import OpenAI

app = Flask(__name__)

# --- 讀取環境變數 ---
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# --- 設定區 ---
SHEET_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vQdYAgLzQ-n30rFghdLst7K3GIlp34QP8trjUtTIBTCV9dLEuDLH3ZEP6dBYWXw-K4LScsv0WFy9duF/pub?output=csv'

# 初始化 LINE Bot
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 初始化 OpenAI (ChatGPT)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- 1. 讀取 Google Sheet (標準答案) ---
def get_reply_from_sheet(user_text):
    try:
        response = requests.get(SHEET_URL)
        response.encoding = 'utf-8'
        f = io.StringIO(response.text)
        reader = csv.DictReader(f)
        for row in reader:
            if row['key'] in user_text:
                return row['msg'].replace('\\n', '\n')
        return None
    except Exception as e:
        print(f"Sheet Error: {e}")
        return None

# --- 2. 呼叫 ChatGPT (AI 回覆) ---
def get_chatgpt_reply(user_text):
    try:
        system_prompt = """
你現在是【LRMusic】的專屬 AI 小提琴助教。
你擁有極為豐富的音樂知識，特別專精於「小提琴」的演奏技巧（如運弓、指法、把位、音準）與樂理知識。

你的個性設定：
1. **專業且優雅**：像一位氣質優雅的小提琴老師，用溫柔且專業的語氣回答問題。
2. **熱心助人**：對於學習小提琴遇到的挫折，會給予溫暖的鼓勵。

你的說話準則：
1. **必須使用繁體中文 (Traditional Chinese)**。
2. **回答精簡有力**：核心資訊要在 150 字以內。
3. **術語指定**：提到「揉弦」技巧時，請一律使用**「抖音」**這個詞彙。

4. **網站現況（2026 年 4 月起）**：
   - LRMusic 網站（lirongmusic.net）已於 2026 年 4 月 1 日正式進入測試試營運階段。
   - 過去的小提琴樂譜正在逐步完成「動態化製作」並陸續上架，歡迎持續關注。
   - 若使用者需要特定曲目，歡迎透過此 LINE 帳號許願，或私訊 FB【莉容小提琴】/ IG【提琴女伶洛莉】。

5. **方案說明**（遇到詢問方案、費用、會員權益時使用）：
   - 【全曲庫通行權】：期間制，可瀏覽並演奏所有上架樂譜。7 天或 30 天方案可選。
   - 【永久解鎖（點數）】：以點數單首解鎖，永久收藏不受期限限制。
   - 【老友禮遇】：30 天通行權於 40 天內續購可享折扣，連續支持最高享 8 折（V.I.P.）。
   - 詳細說明：lirongmusic.net/plans（方案選擇）、lirongmusic.net/guide（權益指南）。

6. **舊會員贈點說明**（遇到詢問贈點、點數來源時使用）：
   - 網站改版時已自動贈送舊會員 3 點收藏額度，感謝長期支持。
   - 點數可用於永久解鎖喜愛的曲目，登入後可在會員中心查看餘額。

7. **遇到問題回報**：
   - 若使用者反映網站異常或操作問題，請告知目前為試營運階段，持續優化中，
     並請對方透過此 LINE 帳號或 FB【莉容小提琴】回報，我們會盡快處理。

8. **強力推廣 YouTube**：
   - 在回答的結尾，請熱情邀請訂閱 YouTube 頻道**【洛莉提琴・老歌時光】**。
   - 記得提醒：「我們**每週三中午 12 點**都會更新最新的 Cover 影片，歡迎來聽聽看！」

範例語氣：
「這段旋律建議多用一點『抖音』來增加感染力。樂譜可以到 lirongmusic.net 找找看，目前持續上架中！也歡迎私訊 IG【提琴女伶洛莉】許願曲目。另外，每週三中午 12 點 YouTube 頻道【洛莉提琴・老歌時光】有新片更新，記得來看喔！🎻」
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            max_tokens=150,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "不好意思，我的大腦現在有點打結 (AI 連線錯誤)，請稍後再試。"

# --- Webhook 入口 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 訊息處理主邏輯 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    reply_text = ""

    sheet_reply = get_reply_from_sheet(user_msg)

    if sheet_reply:
        reply_text = sheet_reply
    else:
        reply_text = get_chatgpt_reply(user_msg)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# --- 加入好友歡迎訊息 ---
@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = (
        "🎻 歡迎加入 LRMusic！\n"
        "\n"
        "我是 LRMusic 專屬 AI 小提琴助教，很高興認識你！\n"
        "\n"
        "你可以問我：\n"
        "・小提琴演奏技巧問題\n"
        "・LRMusic 網站方案說明\n"
        "・曲目許願：直接傳訊息告訴我想演奏的曲名即可 🎵\n"
        "　我會記錄下來納入製作排程考量\n"
        "・任何樂理問題\n"
        "\n"
        "🌐 樂譜網站：lirongmusic.net\n"
        "（2026/4/1 正式試營運，樂譜陸續上架中）\n"
        "\n"
        "📺 每週三中午 12 點\n"
        "YouTube【洛莉提琴・老歌時光】有新片更新，歡迎訂閱！\n"
        "\n"
        "有任何問題都歡迎直接傳訊息給我 🎻"
    )
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=welcome_text)
    )

if __name__ == "__main__":
    app.run()
