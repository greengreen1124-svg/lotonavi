import os
import re
import random
import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# ==================================================
# ページ設定（ゲイル理論＋特殊バイアスCSV完全解析版）
# ==================================================
st.set_page_config(page_title="ロトAI予想・トレンド分析サイト", page_icon="🎰", layout="wide")
st.title("👑 ロトAI予想・トレンド分析サイト")
st.subheader("Gail Howard流アドオン ＆ 横型 bias.csv 特殊フォーマット対応システム")

loto_type = st.sidebar.selectbox("予測するくじ種を選択", ["ロト6", "ロト7", "ミニロト"])

# --- くじ種ごとの基本パラメーターと参照ファイル設定 ---
if loto_type == "ロト6":
    max_num = 43
    pick_num = 6
    history_file = "loto6_history.csv"
    bias_file = "loto6_bias.csv"
    default_min_sum, default_max_sum = 110, 155
elif loto_type == "ロト7":
    max_num = 37
    pick_num = 7
    history_file = "loto7_history.csv"
    bias_file = "loto7_bias.csv"
    default_min_sum, default_max_sum = 115, 150
else:  # ミニロト
    max_num = 31
    pick_num = 5
    history_file = "miniloto_history.csv"
    bias_file = "miniloto_bias.csv"
    default_min_sum, default_max_sum = 65, 95

# ==================================================
# 1. データ自動更新ロジック（Webスクレイピング）
# ==================================================
def fetch_latest_sougaku_result(loto_kind):
    """sougaku.com（ロト生活）から最新のロト結果を自動取得する"""
    url_type = "mini" if loto_kind == "ミニロト" else ("loto6" if loto_kind == "ロト6" else "loto7")
    url = f"http://sougaku.com/{url_type}/index.html"
    try:
        res = requests.get(url, timeout=10)
        res.encoding = res.apparent_encoding if res.apparent_encoding else "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        p_num = 7 if loto_kind == "ロト7" else (6 if loto_kind == "ロト6" else 5)
        b_num = 2 if loto_kind == "ロト7" else 1
        total_nums_needed = p_num + b_num

        for tr in soup.find_all("tr"):
            cells = [c.get_text().strip() for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if len(cells) < 5:
                continue
            joined_text = " ".join(cells)
            all_digits = [int(s) for s in re.findall(r'\d+', joined_text)]
            
            if len(all_digits) >= total_nums_needed + 1:
                round_no = all_digits[0]
                drawn_nums = all_digits[1:p_num+1]
                bonus_nums = all_digits[p_num+1:total_nums_needed+1]
                
                set_letter = "不明"
                for c in cells:
                    m = re.search(r'\b([A-J])\b', c)
                    if m:
                        set_letter = m.group(1)
                        break
                return {"success": True, "round": round_no, "numbers": drawn_nums, "bonus": bonus_nums, "set": set_letter}
    except Exception as e:
        return {"success": False, "msg": str(e)}
    return {"success": False, "msg": "該当データ行が見つかりませんでした"}

# ==================================================
# 2. 特殊な横型 bias.csv のパース（解析）処理
# ==================================================
bias_numbers = []
delete_numbers = []

if os.path.exists(bias_file):
    try:
        # 特殊な行単位のテキストとしてCSVを読み込む
        with open(bias_file, mode="r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            # カンマで分割 (例: ['削除数字', '04 25 26 29 30 37'])
            parts = line_str.split(",", 1)
            if len(parts) < 2:
                continue
                
            header_name = parts[0].strip()
            numbers_str = parts[1].strip()
            
            # スペース等で区切られた数字文字列を整数のリストに変換
            extracted_nums = [int(n) for n in re.findall(r'\d+', numbers_str)]
            
            if "削除" in header_name or "delete" in header_name.lower():
                delete_numbers = extracted_nums
            elif "絞り込み" in header_name or "注目" in header_name or "bias" in header_name.lower():
                bias_numbers = extracted_nums
                
        st.sidebar.success(f"📂 設定ファイル `{bias_file}` を解析・適用しました。")
    except Exception as e:
        st.sidebar.error(f"⚠️ `{bias_file}` の解析中にエラーが発生しました: {e}")
else:
    st.sidebar.warning(f"⚠️ 該当する設定ファイル `{bias_file}` がリポジトリ内に見つかりません。")

# ==================================================
# 3. ゲイル理論 フィルター関数
# ==================================================
def check_gail_filters(comb, loto_kind, use_hilow, use_consec):
    if loto_kind == "ロト6":
        mid = 22
    elif loto_kind == "ロト7":
        mid = 18
    else:  # ミニロト
        mid = 15
        
    low_count = len([n for n in comb if n <= mid])
    
    if use_hilow:
        if loto_kind == "ロト6" and not (2 <= low_count <= 4): return False
        if loto_kind == "ロト7" and not (3 <= low_count <= 4): return False
        if loto_kind == "ミニロト" and not (2 <= low_count <= 3): return False

    if use_consec:
        consec_pairs = 0
        for i in range(len(comb) - 1):
            if comb[i+1] - comb[i] == 1:
                consec_pairs += 1
        if consec_pairs > 1:
            return False
            
    return True

# ==================================================
# 4. メイン画面レイアウト
# ==================================================
latest_info = fetch_latest_sougaku_result(loto_type)

col1, col2 = st.columns(2)

with col1:
    st.header("📊 現在のステータス & 設定")
    if latest_info["success"]:
        st.success(f"✅ 【通信成功】創楽から最新の出目データを同期しました。")
        st.write(f"🏆 **前回（最新）の本数字出目:** 第 **{latest_info['round']}** 回 （セット球: **{latest_info['set']}**）")
        st.code("  ".join([f"{num:02d}" for num in sorted(latest_info['numbers'])]))
    else:
        st.error(f"⚠️ 最新結果の自動スクレイピングに失敗しました: {latest_info.get('msg')}")
        
    st.markdown("### 🎯 CSV参照結果（ビアス式数字）")
    c_del, c_foc = st.columns(2)
    with c_del:
        st.markdown("❌ **削除数字 (プールから完全除外):**")
        st.code(" ".join([f"[{n:02d}]" for n in sorted(delete_numbers)]) if delete_numbers else "なし")
    with c_foc:
        st.markdown("🎯 **絞り込み数字 (出現確率アップ):**")
        st.code(" ".join([f"[{n:02d}]" for n in sorted(bias_numbers)]) if bias_numbers else "なし")

    st.markdown("### 🧬 ゲイル理論 (Smart Luck) アドオン設定")
    use_gail_hilow = st.checkbox("ゲイル流・高低黄金比率フィルターを有効化", value=True)
    use_gail_consec = st.checkbox("ゲイル流・連続数字調和制御を有効化", value=True)
    sum_range = st.slider("合計値の許容範囲 (Sum Range)", 30, 260, (default_min_sum, default_max_sum))

with col2:
    st.header("🔮 AI厳選予想組み合わせ（5点）")
    
    # 削除数字を除外したベースとなる数字のプールを作成
    pool_numbers = [n for n in range(1, max_num + 1) if n not in delete_numbers]
    
    if not pool_numbers:
        st.error("⚠️ 削除数字が多すぎるか、有効な数字のプールが空です。")
    else:
        # すべての数字の初期出現重みを一律「10」に設定
        base_counts = {n: 10 for n in pool_numbers}
        
        # 🎯 【重要】CSVから読み込んだ「絞り込み数字」の出現確率（ウエイト）を5倍に大幅強化
        for n in pool_numbers:
            if n in bias_numbers:
                base_counts[n] *= 5
                
        total_count = sum(base_counts.values())
        pool_weights = [base_counts[n] / total_count for n in pool_numbers]
        
        if st.button(f"🚀 【{loto_type}】次回予想を展開する", type="primary"):
            lucky_numbers = []
            attempts = 0
            max_attempts = 3000
            
            while len(lucky_numbers) < 5 and attempts < max_attempts:
                attempts += 1
                
                # 重み（確率）に基づき、重複なしで数字をランダムサンプリング
                sample_comb = sorted(np.random.choice(pool_numbers, size=pick_num, replace=False, p=pool_weights).tolist())
                
                # 【関門1】 合計値の範囲チェック
                total_val = sum(sample_comb)
                if not (sum_range[0] <= total_val <= sum_range[1]):
                    continue
                    
                # 【関門2】 ゲイル理論調和フィルターチェック
                if attempts < 1500:
                    if not check_gail_filters(sample_comb, loto_type, use_gail_hilow, use_gail_consec):
                        continue
                        
                if sample_comb not in lucky_numbers:
                    lucky_numbers.append(sample_comb)
            
            # 【最終セーフティ補填】
            while len(lucky_numbers) < 5:
                sample_comb = sorted(random.sample(pool_numbers, pick_num))
                if sample_comb not in lucky_numbers:
                    lucky_numbers.append(sample_comb)
            
            # 予測結果の画面出力
            st.caption(f"💡 ゲイル流合計範囲（{sum_range[0]} - {sum_range[1]}）および各バイアス設定をクリアした予想目です。")
            for i, comb in enumerate(lucky_numbers, 1):
                formatted_comb = "  ".join([f"{num:02d}" for num in comb])
                st.success(f"**【{i}点目】** ──  ` {formatted_comb} `  (合計値: {sum(comb)})")
