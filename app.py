import os
import re
import random
import numpy as np
import pandas as pd
import streamlit as st
from collections import Counter

# ==================================================
# ページ設定
# ==================================================
st.set_page_config(page_title="ロトAI予想・トレンド分析サイト", page_icon="🎰", layout="wide")
st.title("👑 ロトAI予想・トレンド分析サイト")
st.subheader("Gail Howard流アドオン ＆ 横型 bias.csv ＆ CSV最新回データ完全参照システム")

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
# 1. データ参照ロジック（CSVファイルから最新回を取得）
# ==================================================
def fetch_latest_csv_result(history_file, pick_num):
    """CSV履歴ファイルから最新（1行目）のロト結果を自動抽出する"""
    if not os.path.exists(history_file):
        return {"success": False, "msg": f"履歴ファイル `{history_file}` が見つかりません"}
    try:
        try:
            df_hist = pd.read_csv(history_file, encoding="utf-8")
        except:
            df_hist = pd.read_csv(history_file, encoding="shift_jis")
        
        if df_hist.empty:
            return {"success": False, "msg": "履歴ファイルが空です"}
            
        # 過去50回集計の仕様（上ほど最新）に合わせ、1行目(インデックス0)を最新回として取得
        latest_row = df_hist.iloc[0]
        
        # 本数字の列を自動抽出（「第○数字」などのヘッダーを検索）
        num_cols = [c for c in df_hist.columns if "第" in c and "数字" in c and "BONUS" not in c and "ボーナス" not in c]
        if not num_cols:
            num_cols = df_hist.columns[2:2+pick_num] # 見つからない場合のフォールバック
            
        drawn_nums = latest_row[num_cols].dropna().astype(int).tolist()
        
        # 回号（回数）列の抽出
        round_col = next((c for c in df_hist.columns if "回" in c or "回数" in c or "回号" in c), df_hist.columns[0])
        round_val = latest_row[round_col]
        try:
            round_no = int(re.search(r'\d+', str(round_val)).group())
        except:
            round_no = round_val
            
        # ボーナス数字列の抽出
        bonus_cols = [c for c in df_hist.columns if "ボーナス" in c or "BONUS" in c]
        bonus_nums = latest_row[bonus_cols].dropna().astype(int).tolist() if bonus_cols else []
        
        # セット球列の抽出
        set_col = next((c for c in df_hist.columns if "セット" in c or "set" in c.lower()), None)
        set_letter = str(latest_row[set_col]).strip() if set_col else "なし"
        
        return {
            "success": True, 
            "round": round_no, 
            "numbers": drawn_nums, 
            "bonus": bonus_nums, 
            "set": set_letter
        }
    except Exception as e:
        return {"success": False, "msg": str(e)}

# ==================================================
# 2. 特殊な横型 bias.csv のパース（解析）処理
# ==================================================
bias_numbers = []
delete_numbers = []

if os.path.exists(bias_file):
    try:
        with open(bias_file, mode="r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in lines:
            line_str = line.strip()
            if not line_str: continue
            parts = line_str.split(",", 1)
            if len(parts) < 2: continue
            header_name = parts[0].strip()
            numbers_str = parts[1].strip()
            extracted_nums = [int(n) for n in re.findall(r'\d+', numbers_str)]
            
            if "削除" in header_name or "delete" in header_name.lower():
                delete_numbers = extracted_nums
            elif "絞り込み" in header_name or "注目" in header_name or "bias" in header_name.lower():
                bias_numbers = extracted_nums
        st.sidebar.success(f"📂 設定ファイル `{bias_file}` を適用しました。")
    except Exception as e:
        st.sidebar.error(f"⚠️ `{bias_file}` 解析エラー: {e}")
else:
    st.sidebar.warning(f"⚠️ `{bias_file}` が見つかりません。")

# ==================================================
# 3. 過去50回の履歴データから出現頻度（スコア）を集計
# ==================================================
score_table = pd.DataFrame(index=range(1, max_num + 1))
score_table["出現回数"] = 0
score_table["グループ"] = "中頻度"
score_table["バイアス設定"] = "通常"

if os.path.exists(history_file):
    try:
        try: df_hist = pd.read_csv(history_file, encoding="utf-8")
        except: df_hist = pd.read_csv(history_file, encoding="shift_jis")
        
        num_cols = [c for c in df_hist.columns if "第" in c and "数字" in c and "BONUS" not in c and "ボーナス" not in c]
        if not num_cols:
            num_cols = df_hist.columns[2:2+pick_num]
            
        df_recent = df_hist.head(50)
        all_past_nums = []
        for col in num_cols:
            all_past_nums.extend(df_recent[col].dropna().astype(int).tolist())
            
        counts = Counter(all_past_nums)
        for n in range(1, max_num + 1):
            score_table.at[n, "出現回数"] = counts.get(n, 0)
            
        # 頻度によるグループ分け
        q_high = score_table["出現回数"].quantile(0.7)
        q_low = score_table["出現回数"].quantile(0.3)
        
        def assign_group(row):
            if row["出現回数"] >= q_high: return "高頻度"
            elif row["出現回数"] <= q_low: return "低頻度"
            return "中頻度"
            
        score_table["グループ"] = score_table.apply(assign_group, axis=1)
    except Exception as e:
        st.sidebar.error(f"⚠️ 過去履歴の集計中にエラーが発生しました: {e}")

# 各数字のバイアス設定ステータスをマッピング
for n in range(1, max_num + 1):
    if n in delete_numbers:
        score_table.at[n, "バイアス設定"] = "❌ 削除数字"
    elif n in bias_numbers:
        score_table.at[n, "バイアス設定"] = "🎯 絞り込み数字"

# ==================================================
# 4. ゲイル理論 フィルター関数
# ==================================================
def check_gail_filters(comb, loto_kind, use_hilow, use_consec):
    if loto_kind == "ロト6": mid = 22
    elif loto_kind == "ロト7": mid = 18
    else: mid = 15
        
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
        if consec_pairs > 1: return False
            
    return True

# ==================================================
# 5. メイン画面レイアウト
# ==================================================
# 創楽の代わりにCSVから最新情報を取得
latest_info = fetch_latest_csv_result(history_file, pick_num)

col1, col2 = st.columns(2)

with col1:
    st.header("📊 現在のステータス & 設定")
    if latest_info["success"]:
        st.success(f"✅ 【同期成功】履歴CSVから最新の出目データを読み込みました。")
        st.write(f"🏆 **前回（最新）の本数字出目:** 第 **{latest_info['round']}** 回 （セット球: **{latest_info['set']}**）")
        st.code("  ".join([f"{num:02d}" for num in sorted(latest_info['numbers'])]))
    else:
        st.error(f"⚠️ 最新結果のCSV読み込み失敗: {latest_info.get('msg')}")
        
    st.markdown("### 🎯 CSV参照結果（ビアス式数字）")
    c_del, c_foc = st.columns(2)
    with c_del:
        st.markdown("❌ **削除数字 (完全除外):**")
        st.code(" ".join([f"[{n:02d}]" for n in sorted(delete_numbers)]) if delete_numbers else "なし")
    with c_foc:
        st.markdown("🎯 **絞り込み数字 (出現確率アップ):**")
        st.code(" ".join([f"[{n:02d}]" for n in sorted(bias_numbers)]) if bias_numbers else "なし")

    st.markdown("### 📈 過去50回のグループ分け簡易要約")
    high_nums = score_table[score_table["グループ"] == "高頻度"].index.tolist()
    mid_nums = score_table[score_table["グループ"] == "中頻度"].index.tolist()
    low_nums = score_table[score_table["グループ"] == "低頻度"].index.tolist()

    st.success(f"**【高頻度（ホット）】** {', '.join([f'{n:02d}' for n in high_nums])}")
    st.warning(f"**【中頻度（ミドル）】** {', '.join([f'{n:02d}' for n in mid_nums])}")
    st.error(f"**【低頻度（コールド）】** {', '.join([f'{n:02d}' for n in low_nums])}")

    # 📊 全数字の詳細スコア内訳表セクション（維持）
    st.markdown("### 📋 全数字のスコア・ステータス詳細内訳表")
    display_table = score_table.copy()
    display_table.index.name = "数字"
    display_table.index = [f"{i:02d}" for i in display_table.index]
    st.dataframe(display_table, use_container_width=True, height=400)

    st.markdown("### 🧬 ゲイル理論 (Smart Luck) アドオン設定")
    use_gail_hilow = st.checkbox("ゲイル流・高低黄金比率フィルターを有効化", value=True)
    use_gail_consec = st.checkbox("ゲイル流・連続数字調和制御を有効化", value=True)
    sum_range = st.slider("合計値の許容範囲 (Sum Range)", 30, 260, (default_min_sum, default_max_sum))

with col2:
    st.header("🔮 AI厳選予想組み合わせ（5点）")
    
    pool_numbers = [n for n in range(1, max_num + 1) if n not in delete_numbers]
    
    if not pool_numbers:
        st.error("⚠️ 有効な数字のプールが空です。")
    else:
        base_weights = {}
        for n in pool_numbers:
            past_count = score_table.at[n, "出現回数"] if n in score_table.index else 0
            base_weights[n] = max(1, past_count)
            
        for n in pool_numbers:
            if n in bias_numbers:
                base_weights[n] *= 5
                
        total_weight = sum(base_weights.values())
        pool_weights = [base_weights[n] / total_weight for n in pool_numbers]
        
        if st.button(f"🚀 【{loto_type}】次回予想を展開する", type="primary"):
            lucky_numbers = []
            attempts = 0
            max_attempts = 3000
            
            while len(lucky_numbers) < 5 and attempts < max_attempts:
                attempts += 1
                sample_comb = sorted(np.random.choice(pool_numbers, size=pick_num, replace=False, p=pool_weights).tolist())
                
                total_val = sum(sample_comb)
                if not (sum_range[0] <= total_val <= sum_range[1]):
                    continue
                    
                if attempts < 1500:
                    if not check_gail_filters(sample_comb, loto_type, use_gail_hilow, use_gail_consec):
                        continue
                        
                if sample_comb not in lucky_numbers:
                    lucky_numbers.append(sample_comb)
            
            while len(lucky_numbers) < 5:
                sample_comb = sorted(random.sample(pool_numbers, pick_num))
                if sample_comb not in lucky_numbers:
                    lucky_numbers.append(sample_comb)
            
            st.caption(f"💡 過去50回のトレンド、各バイアス（CSV）、およびゲイル流合計範囲（{sum_range[0]} - {sum_range[1]}）を完全クリアした予想目です。")
            for i, comb in enumerate(lucky_numbers, 1):
                formatted_comb = "  ".join([f"{num:02d}" for num in comb])
                st.success(f"**【{i}点目】** ──  ` {formatted_comb} `  (合計値: {sum(comb)})")
