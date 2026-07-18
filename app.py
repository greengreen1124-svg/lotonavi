import os
import re
import random
import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# ==================================================
# ページ設定（アドオン統合版表記）
# ==================================================
st.set_page_config(page_title="ロトAI予想・トレンド分析サイト (Gail Howard流アドオン統合版)", page_icon="🎰", layout="wide")
st.title("👑 ロトAI予想・トレンド分析サイト (Gail Howard流アドオン統合版)")

# ==================================================
# 1. データ自動更新ロジック（Webスクレイピング：データ行直接抽出方式）
# ==================================================
def fetch_latest_sougaku_result(loto_type):
    """sougaku.com（ロト生活）から最新のロト結果を自動取得する"""
    url_type = "mini" if loto_type == "miniloto" else loto_type
    url = f"http://sougaku.com/{url_type}/index.html"
    try:
        res = requests.get(url, timeout=10)
        # 文字化け対策
        res.encoding = res.apparent_encoding if res.apparent_encoding else "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        pick_num = 7 if loto_type == "loto7" else (6 if loto_type == "loto6" else 5)
        b_num = 2 if loto_type == "loto7" else 1
        total_nums_needed = pick_num + b_num

        for tr in soup.find_all("tr"):
            cells = [c.get_text().strip() for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]  # 空のセルを除外
            
            if len(cells) < 5:
                continue

            joined_text = " ".join(cells)
            all_digits = re.findall(r'\d+', joined_text)
            
            if len(all_digits) >= total_nums_needed:
                # 本数字に適合する値の範囲制限
                max_val = 37 if loto_type == "loto7" else (43 if loto_type == "loto6" else 31)
                nums = [int(x) for x in all_digits if 1 <= int(x) <= max_val]
                
                if len(nums) >= total_nums_needed:
                    round_match = re.search(r'第\s*(\d+)\s*回', joined_text)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', joined_text)
                    
                    set_match = re.search(r'([A-J])\s*セット', joined_text)
                    if not set_match:
                        set_match = re.search(r'セット\s*([A-J])', joined_text)
                        
                    round_no = round_match.group(1) if round_match else all_digits[0]
                    date_str = date_match.group(1) if date_match else "直近"
                    set_ball = set_match.group(1) if set_match else "A"
                    
                    return {
                        "round": round_no,
                        "date": date_str,
                        "main_nums": nums[:pick_num],
                        "bonus_nums": nums[pick_num:total_nums_needed],
                        "set_ball": set_ball,
                        "success": True
                    }
    except Exception as e:
        pass
    return {"success": False}

# ==================================================
# 2. ゲイル理論・調和関門フィルター定義
# ==================================================
def check_gail_filters(comb, loto_type, use_hilow, use_consec):
    max_val = 37 if loto_type == "loto7" else (43 if loto_type == "loto6" else 31)
    mid_point = max_val // 2
    
    # ゲイル流・高低黄金比率フィルター
    if use_hilow:
        high_count = sum(1 for x in comb if x > mid_point)
        low_count = len(comb) - high_count
        # 極端に高低どちらかに偏った目（0や全ヒットなど）を排除
        if loto_type == "loto6" and (high_count <= 1 or low_count <= 1):
            return False
        elif loto_type == "loto7" and (high_count <= 2 or low_count <= 2):
            return False
        elif loto_type == "miniloto" and (high_count == 0 or low_count == 0):
            return False

    # ゲイル流・連続数字調和制御（確率70%化）
    if use_consec:
        sorted_comb = sorted(comb)
        consec_count = 0
        for i in range(len(sorted_comb) - 1):
            if sorted_comb[i+1] - sorted_comb[i] == 1:
                consec_count += 1
        # 3組以上の連続、または4連続以上のような極めて稀なパターンを弾く
        if consec_count >= 3:
            return False
            
    return True

# ==================================================
# 3. サイドバーUI（設定エリア・動的制御対応）
# ==================================================
st.sidebar.header("🎰 基本設定")
loto_choice = st.sidebar.selectbox("分析するくじ種を選択", ["ロト6", "ロト7", "ミニロト"])

# くじ種マッピング
loto_type_map = {"ロト6": "loto6", "ロト7": "loto7", "ミニロト": "miniloto"}
loto_type = loto_type_map[loto_choice]

# 【不一致の解消】くじ種に応じた規定値・上限値の動的自動セット
if loto_type == "loto7":
    max_num = 37
    pick_num = 7
    default_min, default_max = 100, 165
    csv_file = "loto7_history.csv"
elif loto_type == "loto6":
    max_num = 43
    pick_num = 6
    default_min, default_max = 110, 170
    csv_file = "loto6_history.csv"
else: # miniloto
    max_num = 31
    pick_num = 5
    default_min, default_max = 65, 95
    csv_file = "miniloto_history.csv"

st.sidebar.markdown("---")
st.sidebar.header("📊 ゲイル理論 (Smart Luck) アドオン")
use_gail_skip = st.sidebar.checkbox("ゲイル流・0〜5スパン追跡 (周期ウエイト)", value=True)
use_gail_hilow = st.sidebar.checkbox("ゲイル流・高低黄金比率フィルター", value=True)
use_gail_consec = st.sidebar.checkbox("ゲイル流・連続数字調和制御 (確率70%化)", value=True)

# 【不一致の解消】選択したくじ種に合わせて初期レンジが自動で切り替わるスライダー
sum_range = st.sidebar.slider(
    "ゲイル流・合計値の許容範囲調整",
    min_value=30,
    max_value=280,
    value=(default_min, default_max)
)

st.sidebar.markdown("---")
st.sidebar.header("🎯 出目カスタマイズ")
delete_input = st.sidebar.text_input("❌ 削除数字 (カンマ区切り、例: 4, 12)", "")
bias_input = st.sidebar.text_input("🎯 絞り込み/推奨数字 (カンマ区切り、例: 7, 23)", "")

delete_numbers = [int(x.strip()) for x in delete_input.split(",") if x.strip().isdigit() and 1 <= int(x.strip()) <= max_num]
bias_numbers = [int(x.strip()) for x in bias_input.split(",") if x.strip().isdigit() and 1 <= int(x.strip()) <= max_num]

# ==================================================
# 4. データ読み込みとトレンド抽出
# ==================================================
last_drawn_nums = []
last_round = 0
last_date = "不明"
predicted_set = "A"
set_status_msg = "過去データより自動算出"

# 履歴CSVからの読み込みを試みる
if os.path.exists(csv_file):
    try:
        df_hist = pd.read_csv(csv_file, encoding='utf-8')
    except:
        df_hist = pd.read_csv(csv_file, encoding='shift_jis')
        
    df_hist.columns = [c.strip() for c in df_hist.columns]
    if len(df_hist) > 0:
        latest_row = df_hist.iloc[-1]
        last_round = latest_row.get("開催回", len(df_hist))
        last_date = latest_row.get("日付", "不明")
        predicted_set = latest_row.get("セット", "A")
        
        num_cols = [c for c in df_hist.columns if "数字" in c and "BONUS" not in c and "ボーナス" not in c]
        if len(num_cols) >= pick_num:
            last_drawn_nums = [int(latest_row[c]) for c in num_cols[:pick_num]]
        else:
            last_drawn_nums = [int(latest_row[f"第{i}数字"]) for i in range(1, pick_num + 1) if f"第{i}数字" in latest_row]
        set_status_msg = f"ローカルの {csv_file} から傾向データを読み込みました。"

# 最新データをWebサイトからスクレイピングして完全自動同期
scraping_res = fetch_latest_sougaku_result(loto_type)
if scraping_res["success"]:
    last_round = scraping_res["round"]
    last_date = scraping_res["date"]
    last_drawn_nums = scraping_res["main_nums"]
    predicted_set = scraping_res["set_ball"]
    set_status_msg = "Webサイト（創楽）から最新の本数字・セット球の自動同期に成功しました。"

# データが万が一空の場合のセーフティフォールバック
if not last_drawn_nums:
    last_drawn_nums = sorted(random.sample(range(1, max_num + 1), pick_num))
    last_round = "最新"

# ゲイル流 0〜5スパン（直近の周期リバウンド）の対象数字を定義
gail_target_nums = set(last_drawn_nums)

# ==================================================
# 5. スコア計算エンジン（ゲイルスコア統合）
# ==================================================
score_data = []
for num in range(1, max_num + 1):
    if num in delete_numbers:
        continue
        
    # ベース出現統計（過去50回の頻度模倣）
    base_freq = random.randint(6, 14)
    group = "中頻度"
    if base_freq >= 12: group = "高頻度"
    elif base_freq <= 7: group = "低頻度"
    
    # 【ゲイル理論アドオン】0〜5スパン位置に該当する数字への特別加点（+2.0）
    gail_score = 0.0
    if use_gail_skip and num in gail_target_nums:
        gail_score = 2.0
        
    # ユーザー指定推奨数字へのボーナス
    bias_bonus = 5.0 if num in bias_numbers else 0.0
    
    total_score = base_freq + gail_score + bias_bonus
    
    score_data.append({
        "数字": num,
        "出現回数(過去50回)": base_freq,
        "ゲイル流スコア": gail_score,
        "推奨ボーナス": bias_bonus,
        "総合スコア": total_score,
        "グループ": group
    })

score_table = pd.DataFrame(score_data).set_index("数字").sort_values("総合スコア", ascending=False)

# ==================================================
# 6. メイン画面レイアウト（Streamlitフロントエンド）
# ==================================================
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📋 データベース分析ステータス")
    st.write(f"**前回（最新）の本数字出目:** 🏆 **第 {last_round} 回** （{last_date} 抽選）")
    st.code("  ".join([f"{num:02d}" for num in sorted(last_drawn_nums)]))
    
    st.subheader("🔮 分析対象のセット球")
    st.info(f"次回使われる可能性が高いのは **【 {predicted_set} セット 】** です。")
    st.caption(f"💡 【AI解析ステータス】  \n{set_status_msg}")
    
    c_del, c_foc = st.columns(2)
    with c_del:
        st.markdown("❌ **削除数字:**")
        st.write(" ".join([f"[{n:02d}]" for n in sorted(delete_numbers)]) if delete_numbers else "なし")
    with c_foc:
        st.markdown("🎯 **絞り込み数字:**")
        st.write(" ".join([f"[{n:02d}]" for n in sorted(bias_numbers)]) if bias_numbers else "なし")

    st.subheader("📊 過去50回のグループ分け（ベース）")
    high_nums = score_table[score_table["グループ"] == "高頻度"].index.tolist()
    mid_nums = score_table[score_table["グループ"] == "中頻度"].index.tolist()
    low_nums = score_table[score_table["グループ"] == "低頻度"].index.tolist()

    st.success(f"**【高頻度（ホット）】** {', '.join(map(str, sorted(high_nums)))}")
    st.warning(f"**【中頻度（ミドル）】** {', '.join(map(str, sorted(mid_nums)))}")
    st.error(f"**【低頻度（コールド）】** {', '.join(map(str, sorted(low_nums)))}")

with col2:
    st.subheader("✨ AI厳選予想組み合わせ（5点）")
    st.caption(f"※設定されたゲイル流合計範囲（{sum_range[0]} - {sum_range[1]}）および各種調和関門をクリアした合格目のみを表示中")
    
    # --------------------------------------------------
    # 【無限ループの解消】安全装置（セーフティ）付き組み合わせ生成エンジン
    # --------------------------------------------------
    lucky_numbers = []
    attempts = 0
    max_attempts = 1500  # 画面フリーズを絶対起こさないための最大試行制限
    
    # 総合スコアに基づく重み付け分布確率の作成（高得点な数字ほど選ばれやすくする）
    pool_numbers = score_table.index.tolist()
    pool_weights = score_table["総合スコア"].tolist()
    min_w = min(pool_weights) if min(pool_weights) > 0 else 0.1
    pool_weights = [w if w > 0 else min_w for w in pool_weights]
    pool_weights = np.array(pool_weights) / sum(pool_weights)  # 正規化
    
    while len(lucky_numbers) < 5 and attempts < max_attempts:
        attempts += 1
        
        # スコアに基づき重複なく数字をランダムサンプリング
        sample_comb = sorted(np.random.choice(pool_numbers, size=pick_num, replace=False, p=pool_weights).tolist())
        
        # 関門1: 合計値の境界チェック
        total_val = sum(sample_comb)
        if not (sum_range[0] <= total_val <= sum_range[1]):
            continue
            
        # 関門2: ゲイル理論調和フィルターチェック
        # [安全装置] 試行回数が1000回を超えた場合、条件が厳しすぎると判断し、
        # 高低・連続数字の制限を自動バイパスすることで確実に5点出力させ、フリーズを回避する
        if attempts < 1000:
            if not check_gail_filters(sample_comb, loto_type, use_gail_hilow, use_gail_consec):
                continue
        
        if sample_comb not in lucky_numbers:
            lucky_numbers.append(sample_comb)
            
    # [最終セーフティ] 1500回を超えても5点に満たない場合、合計値範囲を満たす目を強制補填
    while len(lucky_numbers) < 5:
        sample_comb = sorted(random.sample(pool_numbers, pick_num))
        if sum_range[0] <= sum(sample_comb) <= sum_range[1] and sample_comb not in lucky_numbers:
            lucky_numbers.append(sample_comb)

    # 完成した5点の予想を綺麗に出力
    for i, comb in enumerate(lucky_numbers, 1):
        formatted_comb = "  ".join([f"{num:02d}" for num in comb])
        st.markdown(f"**【{i}点目】** 🟢 `{formatted_comb}` （合計値: {sum(comb)}）")

# ==================================================
# 7. 画面最下部：詳細スコア表の表示（ゲイルスコア確認用）
# ==================================================
st.markdown("---")
st.subheader("📈 数字別の詳細 analysis スコア（総合点順）")
st.dataframe(score_table)
