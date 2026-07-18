import os
import re
import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


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

        target_cells = None

        # データ行そのものを直接スキャンして特定する
        for tr in soup.find_all("tr"):
            cells = [c.get_text().strip() for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]  # 空のセルを除外
            
            if len(cells) < 5:
                continue

            joined_text = " ".join(cells)
            all_digits = [int(n) for n in re.findall(r"\d+", joined_text)]

            if len(all_digits) < (total_nums_needed + 1):
                continue

            # 行の中に「回」という文字、または日付（/ や 年月日）の形式が含まれているか
            has_round = any("回" in c for c in cells) or any(re.match(r"^第?\d+回?$", c) for c in cells)
            has_date = any(re.search(r"\d{2,4}[/年-]\d{1,2}[/月-]\d{1,2}", c) for c in cells)

            if has_round and (has_date or len(all_digits) >= total_nums_needed + 2):
                target_cells = cells
                break  # 最新回（通常は一番上の行）が見つかったら終了

        if not target_cells:
            return None, "サイト内から最新の抽選結果データ行を特定できませんでした。"

        round_num = None
        date_str = None
        set_ball = "A"
        pure_numbers = []

        # 1. 開催回の特定
        for c in target_cells:
            r_match = re.search(r"第?(\d+)回", c)
            if r_match:
                round_num = int(r_match.group(1))
                break
        if not round_num and len(target_cells) > 0:
            if re.match(r"^\d+$", target_cells[0]) and int(target_cells[0]) < 3000:
                round_num = int(target_cells[0])

        # 2. 抽選日の特定
        for c in target_cells:
            d_match = re.search(r"(\d{4}|\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", c)
            if d_match:
                year = d_match.group(1)
                if len(year) == 2: year = "20" + year
                date_str = f"{year}/{int(d_match.group(2)):02d}/{int(d_match.group(3)):02d}"
                break

        # 3. セット球の特定 (A-J)
        for c in target_cells:
            s_match = re.search(r"\b([A-J])\b|([A-J])セット|([A-J])球", c.upper())
            if s_match:
                set_ball = [g for g in s_match.groups() if g][0]
                break
            elif len(c) == 1 and c.upper() in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
                set_ball = c.upper()
                break

        # 4. 数字の抽出（日付や回数、セット球以外のセルから純粋に数字を回収）
        for c in target_cells:
            if "回" in c or "年" in c or "/" in c or "-" in c or "セット" in c or c.upper() in ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]:
                continue
            ns = [int(n) for n in re.findall(r"\d+", c)]
            if len(ns) > 0 and len(ns) <= 7:
                pure_numbers.extend(ns)

        if len(pure_numbers) < total_nums_needed:
            raw_digits = [int(n) for n in re.findall(r"\d+", " ".join(target_cells))]
            if len(raw_digits) >= total_nums_needed:
                pure_numbers = raw_digits[-total_nums_needed:]

        if not round_num:
            return None, "開催回の特定に失敗しました。"
        if len(pure_numbers) < total_nums_needed:
            return None, f"数字の個数が足りません。(検出数:{len(pure_numbers)}/必要:{total_nums_needed})"

        result_dict = {
            "round": round_num,
            "date": date_str if date_str else "2026/01/01",
            "numbers": pure_numbers[:pick_num],
            "bonuses": pure_numbers[pick_num:total_nums_needed],
            "set": set_ball,
        }
        return result_dict, None

    except Exception as e:
        return None, f"対象サイトへの接続または解析に失敗しました。({str(e)})"


def append_result_to_csv(file_path, loto_type, result_dict):
    """取得した結果をCSVファイルの末尾に追記する"""
    df = pd.read_csv(file_path)
    
    # 重複チェック用に開催回を確実に数値型にキャスト
    df["開催回"] = pd.to_numeric(df["開催回"], errors='coerce')
    round_num = result_dict["round"]

    if round_num in df["開催回"].values:
        return False, f"第 {round_num} 回の結果は既にCSVに存在するため、スキップしました。"

    new_row = {"開催回": round_num, "日付": result_dict["date"]}

    for i, num in enumerate(result_dict["numbers"], 1):
        new_row[f"第{i}数字"] = num

    cols = df.columns.tolist()

    if loto_type == "loto7":
        new_row["BONUS数字1"] = result_dict["bonuses"][0] if len(result_dict["bonuses"]) > 0 else 0
        new_row["BONUS数字2"] = result_dict["bonuses"][1] if len(result_dict["bonuses"]) > 1 else 0
    else:
        bonus_val = result_dict["bonuses"][0] if len(result_dict["bonuses"]) > 0 else 0
        if "BONUS数字1" in cols:
            new_row["BONUS数字1"] = bonus_val
        elif "BONUS数字" in cols:
            new_row["BONUS数字"] = bonus_val

    if "セット" in cols:
        new_row["セット"] = result_dict["set"]

    new_df = pd.DataFrame([new_row])
    for c in cols:
        if c not in new_df.columns:
            new_df[c] = np.nan
    new_df = new_df[cols]

    updated_df = pd.concat([df, new_df], ignore_index=True)
    updated_df.to_csv(file_path, index=False, encoding="utf-8")
    return True, f"🎉 第 {round_num} 回の結果（{result_dict['set']}セット）をCSVに自動追加しました！"


# ==================================================
# 2. セット球予想ロジック
# ==================================================
def predict_next_set_ball_advanced(df):
    """app-3.pyのロジックに基づくセット球自動予測"""
    if 'セット' not in df.columns or len(df) == 0:
        return "C", "（※CSV内にセットデータがないため、Cセットを選択中）"
        
    set_history = []
    for val in df['セット']:
        m = re.search(r'([A-J_a-j])', str(val))
        set_history.append(m.group(1).upper() if m else "C")
        
    if len(set_history) > 5:
        clean_sets = [s for s in set_history if s in list("ABCDEFGHIJ")]
        if clean_sets:
            current_set = clean_sets[-1]
            transitions = []
            for i in range(len(clean_sets) - 1):
                if clean_sets[i] == current_set: 
                    transitions.append(clean_sets[i+1])
                    
            recent_sets = clean_sets[-30:]
            set_counts = {letter: recent_sets.count(letter) for letter in list("ABCDEFGHIJ")}
            least_frequent_sets = [k for k, v in set_counts.items() if v == min(set_counts.values())]
            
            if transitions:
                predicted_set = max(set(transitions), key=transitions.count)
                status_msg = f"直近【{current_set}】からの遷移確率MAX理論に基づく自動予測"
            elif least_frequent_sets:
                import random
                predicted_set = random.choice(least_frequent_sets)
                status_msg = f"直近30回の未出現ローテーション周期に基づく自動予測"
            else:
                predicted_set = "C"
                status_msg = "自動予測が特定できなかったため、Cセットを選択中"
        else:
            predicted_set = "C"
            status_msg = "有効なセット記号(A-J)が検出されなかったため、Cセットを選択中"
    else:
        predicted_set = "C"
        status_msg = "データ数が少なすぎるため、Cセットを選択中"
        
    return predicted_set, status_msg


def load_forecast(csv_filename):
    delete_numbers = []
    focus_numbers = []
    if os.path.exists(csv_filename):
        for encoding in ['utf-8', 'shift_jis']:
            try:
                with open(csv_filename, 'r', encoding=encoding) as f:
                    for line in f:
                        if '削除数字' in line:
                            parts = line.strip().split(',')
                            if len(parts) >= 2:
                                val = parts[-1]
                                delete_numbers = [int(n) for n in val.split() if n.isdigit()]
                        elif '絞り込み数字' in line:
                            parts = line.strip().split(',')
                            if len(parts) >= 2:
                                val = parts[-1]
                                focus_numbers = [int(n) for n in val.split() if n.isdigit()]
                break
            except:
                continue
    return delete_numbers, focus_numbers


# ==================================================
# 3. バックエンド（分析・予想ロジック ＋ ゲイル理論アドオン）
# ==================================================
def generate_loto_predictions(file_path, loto_type="loto7", num_combinations=5, bias_numbers=None, delete_numbers=None, 
                              target_dow_str=None, user_selected_set="自動", use_gail_skip=True, use_gail_hilow=True, 
                              use_gail_consecutive=True, sum_range=None):
    config = {
        "loto7": {
            "max_num": 37,
            "pick_num": 7,
            "cols": ["第1数字", "第2数字", "第3数字", "第4数字", "第5数字", "第6数字", "第7数字"],
            "all_sets": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        },
        "loto6": {
            "max_num": 43,
            "pick_num": 6,
            "cols": ["第1数字", "第2数字", "第3数字", "第4数字", "第5数字", "第6数字"],
            "all_sets": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        },
        "miniloto": {
            "max_num": 31,
            "pick_num": 5,
            "cols": ["第1数字", "第2数字", "第3数字", "第4数字", "第5数字"],
            "all_sets": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        },
    }

    max_num = config[loto_type]["max_num"]
    pick_num = config[loto_type]["pick_num"]
    main_cols = config[loto_type]["cols"]
    all_sets = config[loto_type]["all_sets"]
    all_numbers = list(range(1, max_num + 1))

    df = pd.read_csv(file_path)
    
    # 開催回を確実に数値型に変換してソート順の不具合を防ぐ
    df["開催回"] = pd.to_numeric(df["開催回"], errors='coerce')
    df = df.dropna(subset=["開催回"])
    df["開催回"] = df["開催回"].astype(int)
    df = df.sort_values(by="開催回").reset_index(drop=True)

    # ゲイル流スパン解析用に過去の本数字リスト（2次元リスト）をパース
    past_numbers = []
    for _, row in df.dropna(subset=main_cols).iterrows():
        past_numbers.append([int(row[c]) for c in main_cols])

    # セット球自動判定
    if user_selected_set == "自動":
        predicted_set, set_status_msg = predict_next_set_ball_advanced(df)
    else:
        predicted_set = user_selected_set
        set_status_msg = f"ユーザー指定により【 {user_selected_set} セット 】に固定して詳細分析を実行中"

    def count_occurrences(target_df):
        counts = pd.Series(target_df[main_cols].values.flatten()).value_counts()
        return counts.reindex(all_numbers, fill_value=0)

    res_50 = count_occurrences(df.tail(50))
    res_10 = count_occurrences(df.tail(10))
    res_5 = count_occurrences(df.tail(5))

    set_df = df[df["セット"] == predicted_set]
    total_set_used = len(set_df)

    if total_set_used > 0:
        set_counts = pd.Series(set_df[main_cols].values.flatten()).value_counts()
        set_rate = (set_counts.reindex(all_numbers, fill_value=0) / total_set_used) * 100
    else:
        set_rate = pd.Series(0, index=all_numbers)

    score_df = pd.DataFrame(index=all_numbers)
    score_df["過去50回スコア"] = res_50 * 1.0
    score_df["直近10回スコア"] = res_10 * 1.5
    score_df["直近5回スコア"] = res_5 * 2.0
    score_df["セット球相性スコア"] = set_rate * 0.3

    score_df["曜日別相性スコア"] = 0.0
    if loto_type == "loto6" and target_dow_str:
        target_dow = 0 if target_dow_str == "月曜日" else 3
        
        df_copy = df.copy()
        df_copy["datetime"] = pd.to_datetime(df_copy["日付"], errors='coerce')
        df_copy["dayofweek"] = df_copy["datetime"].dt.dayofweek
        
        dow_df = df_copy[df_copy["dayofweek"] == target_dow]
        total_dow_used = len(dow_df)
        
        if total_dow_used > 0:
            dow_counts = pd.Series(dow_df[main_cols].values.flatten()).value_counts()
            dow_rate = (dow_counts.reindex(all_numbers, fill_value=0) / total_dow_used) * 100
            score_df["曜日別相性スコア"] = dow_rate * 0.25

    # 📊 ゲイル理論：スキップ回数（経過回数）の解析 ＋ スコア加点システム
    score_df["ゲイル流スコア"] = 0.0
    if use_gail_skip and len(past_numbers) > 0:
        skip_counts = {i: 99 for i in range(1, max_num + 1)}
        for idx, r in enumerate(reversed(past_numbers)):
            for n in r:
                if n in skip_counts and skip_counts[n] == 99:
                    skip_counts[n] = idx  # 0=前回出現, 1=前々回出現...
        for n, skip in skip_counts.items():
            if 0 <= skip <= 5:
                score_df.loc[n, "ゲイル流スコア"] += 2.0  # リバウンド確率の高いスパンに加点

    # 🌟 ビアス式加減点システム
    bias_bonus = 3.0
    score_df["ビアス式スコア"] = 0.0
    if bias_numbers:
        valid_bias = [n for n in bias_numbers if n in all_numbers]
        score_df.loc[valid_bias, "ビアス式スコア"] += bias_bonus
    if delete_numbers:
        valid_delete = [n for n in delete_numbers if n in all_numbers]
        score_df.loc[valid_delete, "ビアス式スコア"] -= bias_bonus  # 削除数字に対してマイナス加点

    score_df["総合スコア"] = (
        score_df["過去50回スコア"] + score_df["直近10回スコア"] + score_df["直近5回スコア"] + 
        score_df["セット球相性スコア"] + score_df["曜日別相性スコア"] + score_df["ゲイル流スコア"] + score_df["ビアス式スコア"]
    )

    summary_df = score_df.sort_values(by="過去50回スコア", ascending=False)
    high_boundary = len(summary_df) // 3
    mid_boundary = (len(summary_df) // 3) * 2
    score_df["グループ"] = "低頻度"
    score_df.iloc[:high_boundary, score_df.columns.get_loc("グループ")] = "高頻度"
    score_df.iloc[high_boundary:mid_boundary, score_df.columns.get_loc("グループ")] = "中頻度"

    # ─── ゲイル理論・調和関門フィルター搭載型組み合わせ生成 ───
    if sum_range is not None:
        sum_min, sum_max = sum_range
    else:
        if loto_type == "loto6": sum_min, sum_max = 110, 170
        elif loto_type == "loto7": sum_min, sum_max = 100, 165
        else: sum_min, sum_max = 65, 95

    weights = score_df["総合スコア"].values
    weights = np.where(weights <= 0, 0.1, weights)
    weights = weights / weights.sum()

    predictions = []
    
    # ゲイルフィルターチェック用のインナールーティン
    def check_gail_filters(nums):
        # 1. 合計値フィルター
        total_sum = sum(nums)
        if not (sum_min <= total_sum <= sum_max): return False
            
        # 2. 高低バランスフィルター（最大値の半分が境界）
        if use_gail_hilow:
            mid_point = max_num // 2
            low_count = len([n for n in nums if n <= mid_point])
            if pick_num == 6 and low_count not in [2, 3, 4]: return False      # ロト6黄金比: 2:4~4:2
            elif pick_num == 7 and low_count not in [2, 3, 4, 5]: return False  # ロト7黄金比: 2:5~5:2
            elif pick_num == 5 and low_count not in [2, 3]: return False        # ミニロト黄金比: 2:3~3:2
            
        # 3. 連続数字調和制御（出現確率70%エミュレート）
        if use_gail_consecutive:
            has_consecutive = any(nums[i+1] - nums[i] == 1 for i in range(len(nums)-1))
            import random
            if not has_consecutive and random.random() < 0.70: return False
            
        return True

    # 第1予想（本命スコア最上位）の抽出を試みる
    scored_numbers = score_df.sort_values(by="総合スコア", ascending=False).index.tolist()
    top_comb = sorted(scored_numbers[:pick_num])
    if check_gail_filters(top_comb):
        predictions.append(top_comb)

    # 対抗トレンド重視の生成
    attempts = 0
    while len(predictions) < num_combinations and attempts < 4000:
        attempts += 1
        chosen = np.random.choice(all_numbers, size=pick_num, replace=False, p=weights)
        chosen_sorted = sorted(list(chosen))
        
        if chosen_sorted in predictions: continue
            
        if check_gail_filters(chosen_sorted):
            predictions.append(chosen_sorted)

    # フィルターが厳しすぎて口数が不足した場合のセーフティバックアップ
    if len(predictions) < num_combinations:
        for _ in range(num_combinations - len(predictions)):
            while True:
                chosen = np.random.choice(all_numbers, size=pick_num, replace=False, p=weights)
                chosen_sorted = sorted(list(chosen))
                if chosen_sorted not in predictions:
                    predictions.append(chosen_sorted)
                    break

    return predicted_set, score_df.sort_values(by="総合スコア", ascending=False), predictions, set_status_msg


# ==================================================
# 4. フロントエンド（Streamlit画面表示）
# ==================================================
st.set_page_config(page_title="ロト予想・分析ナビ ゲイルエディション", layout="wide")

st.title("👑 ロトAI予想・トレンド分析サイト (Gail Howard流アドオン統合版)")
st.caption("過去の出現傾向 × セット球ローテーション × 曜日サイクル × ビアス式加減点 × ゲイル理論黄金比フィルターの融合")

# --- サイドバー設定 ---
st.sidebar.header("⚙️ システム設定")

loto_type = st.sidebar.selectbox("分析するくじ種を選択", ("loto7", "loto6", "miniloto"))
csv_file = f"{loto_type}_history.csv"

st.sidebar.subheader("🔮 セット球の指定")
user_selected_set = st.sidebar.selectbox(
    "分析に使用するセット球を選択",
    ["自動", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
    index=0,
    help="『自動』にすると、過去の遷移から最適なセット球を自動予測します。特定のセット球に固定して相性を分析したい場合はアルファベットを選択してください。"
)

loto6_dow = None
if loto_type == "loto6" and os.path.exists(csv_file):
    try:
        df_temp = pd.read_csv(csv_file)
        df_temp["datetime"] = pd.to_datetime(df_temp["日付"], errors='coerce')
        valid_dates = df_temp["datetime"].dropna()
        if not valid_dates.empty:
            latest_dow = valid_dates.iloc[-1].dayofweek
            default_idx = 1 if latest_dow == 0 else 0
        else:
            default_idx = 0
    except:
        default_idx = 0

    st.sidebar.subheader("📅 ロト6 曜日設定")
    loto6_dow = st.sidebar.selectbox(
        "次回の抽選曜日を選択",
        ("月曜日", "木曜日"),
        index=default_idx,
        help="直近のCSVデータから次回の抽選曜日を自動推測しています。手動で切り替えることも可能です。"
    )

# 外部CSVファイルからのビアス式数字の自動連動管理処理
bias_file = f"{loto_type}_bias.csv"
saved_delete_nums, saved_focus_nums = load_forecast(bias_file)

if f"permanent_bias_{loto_type}" not in st.session_state or st.session_state[f"permanent_bias_{loto_type}"] == "":
    st.session_state[f"permanent_bias_{loto_type}"] = " ".join([f"{n:02d}" for n in saved_focus_nums])

if f"permanent_delete_{loto_type}" not in st.session_state or st.session_state[f"permanent_delete_{loto_type}"] == "":
    st.session_state[f"permanent_delete_{loto_type}"] = " ".join([f"{n:02d}" for n in saved_delete_nums])

st.sidebar.subheader("🔮 ビアス式 絞り込み数字")
bias_input = st.sidebar.text_area(
    f"{loto_type.upper()} の絞り込み数字を入力：",
    value=st.session_state[f"permanent_bias_{loto_type}"],
    help="対応するCSVファイルから自動読込されています。画面上で編集して一時反映することも可能です。",
)
st.session_state[f"permanent_bias_{loto_type}"] = bias_input
bias_numbers = [int(s) for s in re.findall(r"\d+", bias_input)]

st.sidebar.subheader("❌ ビアス式 削除数字")
delete_input = st.sidebar.text_area(
    f"{loto_type.upper()} の削除数字を入力：",
    value=st.session_state[f"permanent_delete_{loto_type}"],
    help="対応するCSVファイルから自動読込されています。画面上で編集して一時反映することも可能です。",
)
st.session_state[f"permanent_delete_{loto_type}"] = delete_input
delete_numbers = [int(s) for s in re.findall(r"\d+", delete_input)]

# 📊 【新設】ゲイル理論アドオン設定エリア
st.sidebar.markdown("---")
st.sidebar.subheader("📊 ゲイル理論 (Smart Luck) アドオン")
g_skip = st.sidebar.checkbox("ゲイル流・0〜5スパン追跡 (周期ウエイト)", value=True, key="sb_g_skip")
g_hilow = st.sidebar.checkbox("ゲイル流・高低黄金比率フィルター", value=True, key="sb_g_hilow")
g_consec = st.sidebar.checkbox("ゲイル流・連続数字調和制御 (確率70%化)", value=True, key="sb_g_consec")

if loto_type == "loto7":
    default_sum_range = (100, 165)
    min_s, max_s = 90, 180
elif loto_type == "loto6":
    default_sum_range = (110, 170)
    min_s, max_s = 80, 200
else:
    default_sum_range = (65, 95)
    min_s, max_s = 40, 130
sum_range = st.sidebar.slider("ゲイル流・合計値の許容範囲調整", min_s, max_s, default_sum_range, key="sb_g_sum")


# データ更新パネル
st.sidebar.markdown("---")
st.sidebar.subheader("📂 CSVデータの更新・追加")

if os.path.exists(csv_file):
    if st.sidebar.button("🌐 ロト生活サイトから最新結果を自動追加"):
        with st.spinner("sougaku.com から最新結果・セット球データを解析中..."):
            result_dict, error = fetch_latest_sougaku_result(loto_type)
            if error:
                st.sidebar.error(error)
            else:
                success, msg = append_result_to_csv(csv_file, loto_type, result_dict)
                if success:
                    st.sidebar.success(msg)
                    st.session_state[f"permanent_bias_{loto_type}"] = ""
                    st.session_state[f"permanent_delete_{loto_type}"] = ""
                    st.rerun()
                else:
                    st.sidebar.warning(msg)

    with st.sidebar.expander("📝 手動で結果を追加する"):
        df_temp = pd.read_csv(csv_file)
        
        df_temp["開催回"] = pd.to_numeric(df_temp["開催回"], errors='coerce')
        next_round = int(df_temp["開催回"].max() + 1) if len(df_temp) > 0 and pd.notna(df_temp["開催回"].max()) else 1

        if len(df_temp) > 0 and "日付" in df_temp.columns:
            latest_date_val = str(df_temp["日付"].iloc[-1])
        else:
            latest_date_val = "2026/01/01"

        m_round = st.number_input("開催回", min_value=1, value=next_round, step=1)
        m_date = st.text_input("抽せん日 (YYYY/MM/DD)", value=latest_date_val)

        p_num = 7 if loto_type == "loto7" else (6 if loto_type == "loto6" else 5)
        b_num = 2 if loto_type == "loto7" else 1

        m_nums_str = st.text_input(f"本数字 ({p_num}個をスペース区切りで)", value="")
        m_bonus_str = st.text_input(f"ボーナス数字 ({b_num}個をスペース区切りで)", value="")
        m_set = st.selectbox("セット球", ("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"))

        if st.button("➕ 手動入力データをCSVに追加"):
            m_nums = [int(s) for s in re.findall(r"\d+", m_nums_str)]
            m_bonus = [int(s) for s in re.findall(r"\d+", m_bonus_str)]

            if len(m_nums) != p_num or len(m_bonus) != b_num:
                st.error("❌ 数字の個数が足りない、または多すぎます。")
            else:
                manual_dict = {
                    "round": m_round,
                    "date": m_date,
                    "numbers": m_nums,
                    "bonuses": m_bonus,
                    "set": m_set,
                }
                success, msg = append_result_to_csv(csv_file, loto_type, manual_dict)
                if success:
                    st.success(msg)
                    st.session_state[f"permanent_bias_{loto_type}"] = ""
                    st.session_state[f"permanent_delete_{loto_type}"] = ""
                    st.rerun()
                else:
                    st.warning(msg)


# --- メイン画面処理 ---
if not os.path.exists(csv_file):
    st.error(f"❌ ファイル `{csv_file}` が見つかりません。フォルダ内に配置してください。")
else:
    df_info = pd.read_csv(csv_file)
    
    df_info["開催回"] = pd.to_numeric(df_info["開催回"], errors='coerce')
    latest_round_in_csv = df_info["開催回"].dropna().max()
    if pd.notna(latest_round_in_csv):
        latest_round_in_csv = int(latest_round_in_csv)
    else:
        latest_round_in_csv = 0
        
    st.caption(f"現在のCSV内の最新データ：**第 {latest_round_in_csv} 回** （データ総数: {len(df_info)}件）")

    # バックエンド分析エンジン起動（ゲイル理論フラグ・合計範囲スライダーを連動）
    predicted_set, score_table, lucky_numbers, set_status_msg = generate_loto_predictions(
        csv_file, loto_type=loto_type, bias_numbers=bias_numbers, delete_numbers=delete_numbers, 
        target_dow_str=loto6_dow, user_selected_set=user_selected_set,
        use_gail_skip=g_skip, use_gail_hilow=g_hilow, use_gail_consecutive=g_consec, sum_range=sum_range
    )

    col1, col2 = st.columns(2)

    with col1:
        if loto_type == "loto6" and loto6_dow:
            st.subheader(f"📅 分析対象の曜日: {loto6_dow}")
            st.info(f"今回は **【 {loto6_dow} 】** の過去データに基づく曜日別相性を加味して分析しています。")

        st.subheader("🔮 分析対象のセット球")
        if user_selected_set == "自動":
            st.info(f"AI自動予測されたセット球は **【 {predicted_set} セット 】** です。")
        else:
            st.success(f"ユーザー指定により **【 {predicted_set} セット 】** で固定分析中。")
        st.caption(f"💡 【AI解析ステータス】  \n{set_status_msg}")

        st.subheader("📡 連動中の外部予想データ（ビアス式）")
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

        st.success(f"**【高頻度（ホット）】** {', '.join(map(str, high_nums))}")
        st.warning(f"**【中頻度（ミドル）** {', '.join(map(str, mid_nums))}")
        st.error(f"**【低頻度（コールド）】** {', '.join(map(str, low_nums))}")

    with col2:
        st.subheader("✨ AI厳選予想組み合わせ（5点）")
        st.caption(f"※設定されたゲイル流合計範囲（{sum_range[0]} - {sum_range[1]}）および各種調和関門をクリアした合格目のみを表示中")
        for i, comb in enumerate(lucky_numbers, 1):
            formatted_comb = "  ".join([f"{num:02d}" for num in comb])
            if i == 1:
                st.success(f"**第 {i} 予想 (本命スコア最上位)** ➔ {formatted_comb}")
            else:
                st.write(f"第 {i} 予想 (対抗トレンド重視) ➔ {formatted_comb}")

    st.markdown("---")
    st.subheader("📈 数字別の詳細 analysis スコア（総合点順）")
    
    # スコア表示列にゲイル流スコアを動的に追加
    show_cols = ["総合スコア", "直近5回スコア", "セット球相性スコア"]
    if loto_type == "loto6":
        show_cols.append("曜日別相性スコア")
    show_cols.extend(["ゲイル流スコア", "ビアス式スコア", "グループ"])
    
    st.dataframe(score_table[show_cols])
