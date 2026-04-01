import os
import requests
import csv
import io
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
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
4. **網站與樂譜詢問**：
   - 樂譜網站目前已開放測試中，歡迎前往使用：lirongmusic.net
   - 若使用者需要特定曲目或有任何問題，也歡迎私訊 FB【莉容小提琴】或 IG【提琴女伶洛莉】詢問。
5. **強力推廣 YouTube**：
   - 在回答的結尾，請熱情邀請訂閱 YouTube 頻道**【洛莉提琴・老歌時光】**。
   - 記得提醒：「我們**每週三中午 12 點**都會更新最新的 Cover 影片，歡迎來聽聽看！」

範例語氣：
「這段旋律建議多用一點『抖音』來增加感染力。樂譜可以到我們的網站 lirongmusic.net 找找看，也歡迎私訊 IG【提琴女伶洛莉】！另外，每週三中午 12 點 YouTube 頻道【洛莉提琴・老歌時光】有新片更新，記得來看喔！🎻」
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

if __name__ == "__main__":
    app.run()
