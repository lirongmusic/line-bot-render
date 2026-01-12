import os
import requests
import csv
import io
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 讀取環境變數
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')

# --- 設定區 ---
# 請將這裡換成你的 Google 試算表 CSV 網址
# 記得網址最後面應該要是 output=csv
SHEET_URL = '請把你的_Google_Sheet_CSV_網址貼在這裡'

line_bot_api = LineBotApi(Y2mnKuvayM6qdO/W89+BZQ0/oeIgHG5mkfbwhTSwom0FbyU44+dU/KztzSTKPoZq1JecGcEPgyogEaFkvJ1oBvFsrr576RcXI0FY0Jlklae8+/z6GHYTfUziEKWAch9KBKKJGVEJcNVbrI9pSjbMBQdB04t89/1O/w1cDnyilFU=)
handler = WebhookHandler(908eea58ffed664f86dd4bc1fb9f8e30)

# --- 讀取 Google Sheet 的函式 ---
def get_reply_from_sheet(user_text):
    try:
        # 下載 CSV 檔案
        response = requests.get(https://docs.google.com/spreadsheets/d/e/2PACX-1vQdYAgLzQ-n30rFghdLst7K3GIlp34QP8trjUtTIBTCV9dLEuDLH3ZEP6dBYWXw-K4LScsv0WFy9duF/pub?output=csv)
        response.encoding = 'utf-8' # 設定編碼以免中文亂碼
        
        # 解析 CSV
        f = io.StringIO(response.text)
        reader = csv.DictReader(f)
        
        # 搜尋關鍵字
        for row in reader:
            # row['key'] 是 A 欄，row['msg'] 是 B 欄
            if row['key'] in user_text:
                return row['msg'].replace('\\n', '\n') # 處理換行符號
                
        return None # 找不到對應關鍵字
        
    except Exception as e:
        print(f"讀取試算表失敗: {e}")
        return None

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    # 1. 先去 Google Sheet 找答案
    sheet_reply = get_reply_from_sheet(user_msg)
    
    if sheet_reply:
        reply_text = sheet_reply
    else:
        # 2. 如果 Sheet 裡沒設定，就執行預設邏輯 (或是接 ChatGPT)
        if user_msg == "查ID":
            reply_text = f"你的 User ID 是：{event.source.user_id}"
        else:
            reply_text = "抱歉，我還在學習中。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run()