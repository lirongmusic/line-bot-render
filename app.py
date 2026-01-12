import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 修改區：改為讀取環境變數 (安全版) ---
# 之後我們會在 Render 的後台設定這兩個變數
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')

# 檢查是否成功讀取 (除錯用)
if CHANNEL_ACCESS_TOKEN is None or CHANNEL_SECRET is None:
    print("錯誤：找不到環境變數！請確認是否已設定。")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

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




# --- 修改後的訊息處理邏輯 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 取得使用者傳來的文字
    user_msg = event.message.text.strip() # .strip() 可以移除前後多餘的空白
    
    reply_text = "" # 準備要回覆的文字

    # --- 關鍵字判斷邏輯 ---
    if user_msg == "你好":
        reply_text = "哈囉！我是你的專屬小編，有什麼我可以幫你的嗎？"
        
    elif user_msg == "網站":
        reply_text = "https://lirongmusic.net/ 網站尚在維護升級中，敬請期待！"
        
        
    else:
        # 如果沒有對應的關鍵字，就回覆預設訊息，或是重複他的話
        reply_text = f"你剛剛說了：「{user_msg}」，但我還在學習中，只聽得懂「你好」喔！"

    # 發送回覆
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


if __name__ == "__main__":
    app.run()