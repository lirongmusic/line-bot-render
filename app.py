import os
import requests
import csv
import io
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from openai import OpenAI  # 引入 OpenAI 工具

app = Flask(__name__)

# --- 讀取環境變數 ---
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') # 新增這行

# --- 設定區 ---
# 你的 Google Sheet CSV 網址
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
        # 設定 AI 的角色 (System Prompt)
        # 你可以在這裡修改 AI 的個性
        system_prompt = "你是一個專業、親切的客服小編。請用繁體中文回答，盡量簡短有力 (100字以內)。"

        response = client.chat.completions.create(
            model="gpt-4o-mini", # 使用最划算且快速的模型
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            max_tokens=150, # 限制回覆長度，節省成本
            temperature=0.7, # 創意程度 (0.7 比較自然)
        )
        # 取得 AI 的回答
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

    # 步驟 A: 先去 Google Sheet 找答案
    sheet_reply = get_reply_from_sheet(user_msg)
    
    if sheet_reply:
        # 如果試算表有，就用試算表的答案
        reply_text = sheet_reply
    else:
        # 步驟 B: 如果試算表沒有，就問 ChatGPT
        reply_text = get_chatgpt_reply(user_msg)

    # 發送回覆
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()