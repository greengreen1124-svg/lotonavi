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
    url = f"http://sougaku.com/{loto_type}/index.html"
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
# 2. バックエンド（分析・予想ロジック：曜日別分析追加版）
# ==================================================
def generate_loto_predictions(file_path, loto_type="loto7", num_combinations=5, bias_numbers=None, target_dow_str=None):
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
    df = df.sort_values(by="開催回").reset_index(drop=True)

    # セット球の予想
    recent_10_sets = df.tail(10)["セット"].value_counts().reindex(all_sets, fill_value=0)
    predicted_set = recent_10_sets.sort_values(ascending=True).index[0]

    # 出現回数の集計
    def count_occurrences(target_df):
        counts = pd.Series(target_df[main_cols].values.flatten()).value_counts()
        return counts.reindex(all_numbers, fill_value=0)

    res_50 = count_occurrences(df.tail(50))
    res_10 = count_occurrences(df.tail(10))
    res_5 = count_occurrences(df.tail(5))

    # セット球相性
    set_df = df[df["セット"] == predicted_set]
    total_set_used = len(set_df)

    if total_set_used > 0:
        set_counts = pd.Series(set_df[main_cols].values.flatten()).value_counts()
        set_rate = (set_counts.reindex(all_numbers, fill_value=0) / total_set_used) * 100
    else:
        set_rate = pd.Series(0, index=all_numbers)

    # 総合スコアリング
    score_df = pd.DataFrame(index=all_numbers)
    score_df["過去50回スコア"] = res_50 * 1.0
    score_df["直近10回スコア"] = res_10 * 1.5
    score_df["直近5回スコア"] = res_5 * 2.0
    score_df["セット球相性スコア"] = set_rate * 0.3

    # 【新機能】ロト6のみ：曜日別相性スコアの計算
    score_df["曜日別相性スコア"] = 0.0
    if loto_type == "loto6" and target_dow_str:
        target_dow = 0 if target_dow_str == "月曜日" else 3  # 0=月曜, 3=木曜
        
        df_copy = df.copy()
        df_copy["datetime"] = pd.to_datetime(df_copy["日付"], errors='coerce')
        df_copy["dayofweek"] = df_copy["datetime"].dt.dayofweek
        
        # 特定の曜日データのみを抽出
        dow_df = df_copy[df_copy["dayofweek"] == target_dow]
        total_dow_used = len(dow_df)
        
        if total_dow_used > 0:
            dow_counts = pd.Series(dow_df[main_cols].values.flatten()).value_counts()
            dow_rate = (dow_counts.reindex(all_numbers, fill_value=0) / total_dow_used) * 100
            score_df["曜日別相性スコア"] = dow_rate * 0.25  # 曜日傾向の重み付け

    # ビアス式スコアは 3.0 固定
    bias_bonus = 3.0
    score_df["ビアス式スコア"] = 0.0
    if bias_numbers:
        valid_bias = [n for n in bias_numbers if n in all_numbers]
        score_df.loc[valid_bias, "ビアス式スコア"] = bias_bonus

    # 総合スコアに「曜日別相性スコア」を合算
    score_df["総合スコア"] = (
        score_df["過去50回スコア"] + score_df["直近10回スコア"] + score_df["直近5回スコア"] + 
        score_df["セット球相性スコア"] + score_df["曜日別相性スコア"] + score_df["ビアス式スコア"]
    )

    # グループ分け
    summary_df = score_df.sort_values(by="過去50回スコア", ascending=False)
    high_boundary = len(summary_df) // 3
    mid_boundary = (len(summary_df) // 3) * 2
    score_df["グループ"] = "低頻度"
    score_df.iloc[:high_boundary, score_df.columns.get_loc("グループ")] = "高頻度"
    score_df.iloc[high_boundary:mid_boundary, score_df.columns.get_loc("グループ")] = "中頻度"

    # 予想組み合わせ生成
    scored_numbers = score_df.sort_values(by="総合スコア", ascending=False).index.tolist()
    predictions = []
    predictions.append(sorted(scored_numbers[:pick_num]))

    weights = score_df["総合スコア"].values
    weights = np.where(weights <= 0, 0.1, weights)
    weights = weights / weights.sum()

    for _ in range(num_combinations - 1):
        while True:
            chosen = np.random.choice(all_numbers, size=pick_num, replace=False, p=weights)
            chosen_sorted = sorted(list(chosen))
            if chosen_sorted not in predictions:
                predictions.append(chosen_sorted)
                break

    return predicted_set, score_df.sort_values(by="総合スコア", ascending=False), predictions


# ==================================================
# 3. フロントエンド（Streamlit画面表示）
# ==================================================
st.set_page_config(page_title="ロト予想・分析ナビ", layout="wide")

st.title("🎯 ロトAI予想・トレンド分析サイト")
st.caption("過去の出現傾向 × セット球ローテーション × 曜日別サイクル（LOTO6） × ビアス式絞り込みの融合システム")

# --- サイドバー設定 ---
st.sidebar.header("⚙️ システム設定")

loto_type = st.sidebar.selectbox("分析するくじ種を選択", ("loto7", "loto6", "miniloto"))
csv_file = f"{loto_type}_history.csv"

# 【新機能】ロト6専用の曜日選択パネル＆自動曜日推測
loto6_dow = None
if loto_type == "loto6" and os.path.exists(csv_file):
    try:
        df_temp = pd.read_csv(csv_file)
        df_temp["datetime"] = pd.to_datetime(df_temp["日付"], errors='coerce')
        valid_dates = df_temp["datetime"].dropna()
        if not valid_dates.empty:
            latest_dow = valid_dates.iloc[-1].dayofweek
            # 直近が月曜(0)なら次回は木曜(idx:1)、木曜(3)なら次回は月曜(idx:0)
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

# 永続保存用のセッションキー管理
for lt, default_val in [
    ("loto7", "06 07 08 09 10 11 12 16 17 18 20 21 22 23 24 26 27 28 29 31 32 33 34 36"),
    ("loto6", ""),
    ("miniloto", "")
]:
    if f"permanent_bias_{lt}" not in st.session_state:
        st.session_state[f"permanent_bias_{lt}"] = default_val

st.sidebar.subheader("🔮 ビアス式 絞り込み数字")
bias_input = st.sidebar.text_area(
    f"{loto_type.upper()} の絞り込み数字を入力：",
    value=st.session_state[f"permanent_bias_{loto_type}"],
    help="対象URLの『ビアス式絞り込み予想』の下にある数字をコピーして貼り付けてください。",
)
st.session_state[f"permanent_bias_{loto_type}"] = bias_input
bias_numbers = [int(s) for s in re.findall(r"\d+", bias_input)]

# データ更新パネル
st.sidebar.markdown("---")
st.sidebar.subheader("📂 CSVデータの更新・追加")

if os.path.exists(csv_file):
    # ① 指定サイトから自動取得ボタン
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
                    st.rerun()
                else:
                    st.sidebar.warning(msg)

    # ② バックアップ用：手動追加フォーム
    with st.sidebar.expander("📝 手動で結果を追加する"):
        df_temp = pd.read_csv(csv_file)
        next_round = int(df_temp["開催回"].max() + 1) if len(df_temp) > 0 else 1

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
                    st.rerun()
                else:
                    st.warning(msg)


# --- メイン画面処理 ---
if not os.path.exists(csv_file):
    st.error(f"❌ ファイル `{csv_file}` が見つかりません。フォルダ内に配置してください。")
else:
    df_info = pd.read_csv(csv_file)
    latest_round_in_csv = df_info["開催回"].max()
    st.caption(f"現在のCSV内の最新データ：**第 {latest_round_in_csv} 回** （データ総数: {len(df_info)}件）")

    # 予想実行 (新引数 target_dow_str を引き渡し)
    predicted_set, score_table, lucky_numbers = generate_loto_predictions(
        csv_file, loto_type=loto_type, bias_numbers=bias_numbers, target_dow_str=loto6_dow
    )

    col1, col2 = st.columns(2)

    with col1:
        # ロト6の場合、適用している曜日設定をアナウンス
        if loto_type == "loto6" and loto6_dow:
            st.subheader(f"📅 分析対象の曜日: {loto6_dow}")
            st.info(f"今回は **【 {loto6_dow} 】** の過去データに基づく曜日別相性を加味して分析しています。")

        st.subheader("🔮 次回の予想セット球")
        st.info(f"次回使われる可能性が高いのは **【 {predicted_set} セット 】** です。")
        st.write("※根拠：直近10回の抽選で出現回数が最も少なく、次回のローテーションで選ばれる確率が一番高いため。")

        st.subheader("📊 過去50回のグループ分け（ベース）")
        high_nums = score_table[score_table["グループ"] == "高頻度"].index.tolist()
        mid_nums = score_table[score_table["グループ"] == "中頻度"].index.tolist()
        low_nums = score_table[score_table["グループ"] == "低頻度"].index.tolist()

        st.success(f"**【高頻度（ホット）】** {', '.join(map(str, high_nums))}")
        st.warning(f"**【中頻度（ミドル）】** {', '.join(map(str, mid_nums))}")
        st.error(f"**【低頻度（コールド）】** {', '.join(map(str, low_nums))}")

    with col2:
        st.subheader("✨ AI厳選予想組み合わせ（5点）")
        for i, comb in enumerate(lucky_numbers, 1):
            formatted_comb = "  ".join([f"{num:02d}" for num in comb])
            if i == 1:
                st.success(f"**第 {i} 予想 (本命スコア最上位)** ➔ {formatted_comb}")
            else:
                st.write(f"第 {i} 予想 (対抗トレンド重視) ➔ {formatted_comb}")

    st.markdown("---")
    st.subheader("📈 数字別の詳細分析スコア（総合点順）")
    
    # ロト6の時だけ「曜日別相性スコア」の列を表示に含める
    if loto_type == "loto6":
        st.dataframe(score_table[["総合スコア", "直近5回スコア", "セット球相性スコア", "曜日別相性スコア", "ビアス式スコア", "グループ"]])
    else:
        st.dataframe(score_table[["総合スコア", "直近5回スコア", "セット球相性スコア", "ビアス式スコア", "グループ"]])