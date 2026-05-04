import os
import requests
import csv
import io
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FollowEvent,
    QuickReply, QuickReplyButton, MessageAction,
)
from openai import OpenAI

app = Flask(__name__)

# --- 讀取環境變數 ---
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET       = os.environ.get('CHANNEL_SECRET')
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')

# --- 設定區 ---
SHEET_URL = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vQdYAgLzQ-n30rFghdLst7K3GIlp34QP8trjUtTIBTCV9dLEuDLH3ZEP6dBYWXw-K4LScsv0WFy9duF/pub?output=csv'

# WordPress 網站設定（Line 綁定查詢 + 許願 API 用）
LRM_SITE_URL    = 'https://lirongmusic.net'
LRM_CRON_SECRET = os.environ.get('LRM_CRON_SECRET', '')  # 從環境變數讀取

# 許願模組設定（LRM_SITE_URL 須先定義）
WP_WISHES_URL = f'{LRM_SITE_URL}/wp-json/lrmusic/v1/wishes'

# 用戶許願對話狀態（記憶體，Render 重啟後清空，屬正常現象）
# 格式：{ line_user_id: { 'step': 1, 'song_title': '', 'artist': '' } }
user_states = {}

# 許願類別 Quick Reply 選項（key, 顯示文字）
WISH_CATEGORIES = [
    ('anime',   '🎌 日本動漫'),
    ('kdrama',  '🎬 韓劇 OST'),
    ('cpop',    '🎤 華語流行'),
    ('western', '🎸 西洋經典'),
    ('other',   '📌 其他'),
]

# 觸發許願流程的關鍵字
WISH_TRIGGER_KEYWORDS = ['許願', '我要許願', '許個願', 'wish']

# 觸發排行榜的關鍵字
RANK_TRIGGER_KEYWORDS = ['排行榜', '許願排行', '排行', '熱門許願']

# 初始化 LINE Bot
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 初始化 OpenAI (ChatGPT)
client = OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# 0. 查詢 WordPress 會員綁定狀態
# ============================================================
def get_wp_user_by_line_id(line_user_id):
    """查詢此 Line ID 是否已綁定 WordPress 帳號，回傳會員資料或 None"""
    try:
        r = requests.get(
            f'{LRM_SITE_URL}/wp-json/lrmusic/v1/user/get-by-line-id',
            params={'line_user_id': line_user_id},
            headers={'X-LRM-Secret': LRM_CRON_SECRET},
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            if data.get('found'):
                return data  # {'wp_user_id': 123, 'email': '...', 'first_name': '...'}
    except Exception as e:
        print(f'[LRMusic] 查詢綁定狀態失敗：{e}')
    return None


# ============================================================
# 1. 讀取 Google Sheet（標準答案）
# ============================================================
def get_reply_from_sheet(user_text):
    try:
        response = requests.get(SHEET_URL)
        response.encoding = 'utf-8'
        f = io.StringIO(response.text)
        reader = csv.DictReader(f)
        rows = list(reader)

        # 檢查機器人開關（key = __bot_enabled__，msg = false 時靜音）
        for row in rows:
            if row['key'].strip() == '__bot_enabled__':
                if row['msg'].strip().lower() == 'false':
                    return '__SILENT__'
                break

        for row in rows:
            if row['key'] in user_text:
                return row['msg'].replace('\\n', '\n')
        return None
    except Exception as e:
        print(f"Sheet Error: {e}")
        return None


# ============================================================
# 2. 呼叫 ChatGPT（AI 回覆）
# ============================================================
def get_chatgpt_reply(user_text, wp_user=None):
    """
    呼叫 GPT 產生回覆。
    若 wp_user 不為 None，代表用戶已綁定 WordPress 帳號，
    可在 system prompt 中插入個人化資訊。
    """
    try:
        # 若已綁定，在 prompt 加入用戶名字
        user_name_hint = ''
        if wp_user and wp_user.get('first_name'):
            user_name_hint = f'\n\n【用戶資訊】這位用戶已綁定 LRMusic 帳號，名字是「{wp_user["first_name"]}」，可以在適當時機稱呼對方名字。'

        system_prompt = """
你現在是【LRMusic 音樂小助教】，LRMusic 的專屬 AI 小提琴助教。
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
   - 部分曲目支援**切換中提琴樂譜**，功能陸續更新中，中提琴學習者也適用。
   - **永久收藏（💎 點數解鎖）會員**可在播放器工具列下載該曲的 PDF 樂譜檔，方便離線練習。
   - LRMusic **不提供鋼琴伴奏譜**，專注於弦樂譜。若使用者詢問鋼琴譜，告知不提供，但可提供代購及改譜服務，請對方私訊洽詢。
   - 若使用者需要特定曲目，歡迎透過此 LINE 帳號許願（輸入「許願」即可開始）。

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

8. **強力推廣 YouTube 雙頻道**：
   - 洛莉現在有兩個 YouTube 頻道，請依情境推薦：
     - **【洛莉提琴・老歌時光】**（@LRMusicOldies）：國語老歌小提琴 Cover，每週三中午 12 點更新
     - **【LRMusic Violin】**（@LRMusicViolin）：日本動漫、韓劇 OST、華語流行、西洋經典，每週五中午 12 點更新
   - 若使用者詢問的曲目屬於國語老歌，優先推薦老歌時光頻道；若屬於動漫、韓劇、流行，優先推薦 LRMusic Violin。
   - 不確定時，兩個頻道都介紹。

範例語氣：
「這段旋律建議多用一點『抖音』來增加感染力。樂譜可以到 lirongmusic.net 找找看，目前持續上架中！也歡迎私訊 IG【提琴女伶洛莉】許願曲目。另外，洛莉有兩個 YouTube 頻道：喜歡國語老歌的可以訂閱【洛莉提琴・老歌時光】，每週三中午 12 點更新；喜歡動漫、韓劇 OST 的可以訂閱【LRMusic Violin】，每週五中午 12 點更新，歡迎來聽聽看！🎻」
""" + user_name_hint

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


# ============================================================
# 許願模組輔助函式
# ============================================================

def wish_create(line_user_id, song_title, artist, category):
    """呼叫 WordPress REST API 新增許願，回傳 (success, message)"""
    # 先查 WP 帳號綁定狀態
    wp_user = get_wp_user_by_line_id(line_user_id)
    if not wp_user:
        return False, (
            '你尚未綁定 LRMusic 網站帳號，無法許願。\n\n'
            '請前往 https://lirongmusic.net 以 Google 帳號登入，\n'
            '再於帳號頁面完成 LINE 綁定即可 🎻'
        )

    try:
        resp = requests.post(
            WP_WISHES_URL,
            json={
                'song_title':   song_title,
                'artist':       artist,
                'category':     category,
                'line_user_id': line_user_id,
                'wp_user_id':   wp_user.get('wp_user_id', 0),
            },
            headers={
                'Content-Type': 'application/json',
                'X-LRM-Secret': LRM_CRON_SECRET,
            },
            timeout=8
        )
        data = resp.json()

        if resp.status_code in (200, 201) and data.get('success'):
            rank       = data.get('rank', '?')
            artist_str = f' — {artist}' if artist else ''
            return True, (
                f'🎵 許願成功！\n\n'
                f'「{song_title}」{artist_str}\n'
                f'目前排名第 {rank} 名 🎻\n\n'
                f'🗳️ 完整排行：https://lirongmusic.net/wishes'
            )
        elif resp.status_code == 409:
            rank = data.get('rank', '?')
            return False, f'你已經許願過「{song_title}」了！\n目前排名第 {rank} 名。'
        else:
            msg = data.get('message', '未知錯誤')
            return False, f'許願失敗：{msg}'

    except Exception as e:
        print(f'[LRMusic] wish_create 錯誤：{e}')
        return False, '系統暫時無法處理，請稍後再試。'


def wish_get_ranking():
    """取得 Top 5 排行榜，回傳格式化文字"""
    try:
        resp = requests.get(WP_WISHES_URL, params={'limit': 5}, timeout=8)
        data = resp.json()
        wishes = data.get('wishes', [])

        if not wishes:
            return '目前還沒有許願紀錄，快來許第一個願吧！🎶\n\n輸入「許願」即可開始 🎻'

        medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']
        lines  = ['🎵 許願排行榜 Top 5\n']
        for i, w in enumerate(wishes):
            artist_str = f' — {w["artist"]}' if w.get('artist') else ''
            lines.append(f'{medals[i]} {w["song_title"]}{artist_str}（{w["vote_count"]} 票）')

        lines.append('\n🗳️ 完整排行：https://lirongmusic.net/wishes')
        return '\n'.join(lines)

    except Exception as e:
        print(f'[LRMusic] wish_get_ranking 錯誤：{e}')
        return '暫時無法取得排行榜，請稍後再試。'


def wish_make_category_quick_reply():
    """產生類別選擇的 Quick Reply 物件"""
    items = [
        QuickReplyButton(action=MessageAction(label=label, text=label))
        for _, label in WISH_CATEGORIES
    ]
    return QuickReply(items=items)


def wish_label_to_key(label):
    """將類別顯示文字轉回資料庫 key，找不到回傳 'other'"""
    for key, lbl in WISH_CATEGORIES:
        if lbl == label:
            return key
    return 'other'


# ============================================================
# Webhook 入口
# ============================================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


# ============================================================
# 訊息處理主邏輯
# ============================================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg     = event.message.text.strip()
    line_user_id = event.source.user_id

    # ── 許願狀態機（優先於 Sheet / AI）──────────────────────
    state = user_states.get(line_user_id)

    # Step 1：等待用戶輸入曲名
    if state and state['step'] == 1:
        user_states[line_user_id]['song_title'] = user_msg
        user_states[line_user_id]['step'] = 2
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='🎤 請輸入原唱 / 演唱者名稱\n（不知道或想略過請輸入「略過」）')
        )
        return

    # Step 2：等待用戶輸入演唱者
    if state and state['step'] == 2:
        artist = '' if user_msg in ('略過', '跳過', '-', '無') else user_msg
        user_states[line_user_id]['artist'] = artist
        user_states[line_user_id]['step']   = 3
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(
                text='🎵 最後，這首歌屬於哪個類別？',
                quick_reply=wish_make_category_quick_reply()
            )
        )
        return

    # Step 3：等待用戶選擇類別（Quick Reply 或手動輸入皆可）
    if state and state['step'] == 3:
        category  = wish_label_to_key(user_msg)
        song      = state['song_title']
        artist    = state['artist']
        del user_states[line_user_id]  # 清除狀態，避免佔用記憶體

        _success, reply_text = wish_create(line_user_id, song, artist, category)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    # 排行榜觸發
    if any(kw in user_msg for kw in RANK_TRIGGER_KEYWORDS):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=wish_get_ranking())
        )
        return

    # 許願觸發（開始對話流程）
    if any(kw in user_msg for kw in WISH_TRIGGER_KEYWORDS):
        user_states[line_user_id] = {'step': 1, 'song_title': '', 'artist': ''}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='🎻 好的！請輸入你想許願的曲名：')
        )
        return
    # ── 許願狀態機結束 ────────────────────────────────────────

    # 查詢是否已綁定 WordPress 帳號（供 GPT 個性化回覆用）
    wp_user = get_wp_user_by_line_id(line_user_id)

    sheet_reply = get_reply_from_sheet(user_msg)

    # 靜音模式：試算表開關設為 false，直接不回應
    if sheet_reply == '__SILENT__':
        return

    if sheet_reply:
        reply_text = sheet_reply
    else:
        reply_text = get_chatgpt_reply(user_msg, wp_user=wp_user)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )


# ============================================================
# 加入好友歡迎訊息
# ============================================================
@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = (
        "🎻 歡迎加入 LRMusic！\n"
        "\n"
        "我是 LRMusic 音樂小助教，很高興認識你！\n"
        "\n"
        "你可以問我：\n"
        "・小提琴演奏技巧問題\n"
        "・LRMusic 網站方案說明\n"
        "・曲目許願：輸入「許願」即可開始 🎵\n"
        "・排行榜：輸入「排行榜」查看大家最想聽什麼\n"
        "・任何樂理問題\n"
        "\n"
        "🌐 樂譜網站：lirongmusic.net\n"
        "（2026/4/1 正式試營運，樂譜陸續上架中）\n"
        "・部分曲目支援切換中提琴樂譜，陸續更新中 🎻\n"
        "・永久收藏（💎 點數解鎖）會員可下載 PDF 樂譜檔\n"
        "\n"
        "📺 YouTube 雙頻道，歡迎訂閱！\n"
        "・【洛莉提琴・老歌時光】每週三中午 12 點（國語老歌）\n"
        "・【LRMusic Violin】每週五中午 12 點（動漫・韓劇・流行）\n"
        "\n"
        "有任何問題都歡迎直接傳訊息給我 🎻"
    )
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=welcome_text)
    )


if __name__ == "__main__":
    app.run()
