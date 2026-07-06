import datetime
import os
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup


def update_bias_numbers_daily(loto_type):
    """1日に1回サイトを確認し、ビアス式数字に更新があればCSVをアップデートする関数"""

    # 1. 保存用CSVと、最終確認日を記録するテキストファイルの名前を設定
    csv_filename = f"{loto_type}_bias_current.csv"
    check_log_file = f"{loto_type}_bias_last_check.txt"

    today_str = datetime.date.today().isoformat()  # 例: "2026-07-06"

    # 2. 【1日1回制御】今日すでに確認済みかチェック
    if os.path.exists(check_log_file):
        with open(check_log_file, "r", encoding="utf-8") as f:
            last_check_date = f.read().strip()

        # 今日すでに確認済みなら、サイトにはアクセスせず既存のCSVを読み込む
        if last_check_date == today_str:
            if os.path.exists(csv_filename):
                df_cache = pd.read_csv(csv_filename)
                return (
                    df_cache["numbers"].tolist(),
                    "ℹ️ 本日のビアス式数字は確認済みです（ローカルCSVからロード）。",
                )

    # 3. 【スクレイピング】今日まだ未確認ならサイトを見に行く
    urls = {
        "ロト7": "http://sougaku.com/loto7/index.html",
        "ロト6": "http://sougaku.com/loto6/index.html",
        "ミニロト": "http://sougaku.com/miniloto/index.html",
    }
    url = urls[loto_type]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding

        if response.status_code != 200:
            raise Exception(f"HTTPエラー: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")

        # 「星の魔法陣」周辺のテキストを抽出
        target_text = ""
        for tag in soup.find_all(
            string=re.compile(r"星の魔法陣|絞り込んでみた|魔法陣")
        ):
            parent = tag.find_parent()
            if parent:
                target_text += parent.get_text() + "\n"
            curr = tag
            for _ in range(4):  # 直後の要素も回収
                nxt = curr.find_next()
                if nxt:
                    target_text += nxt.get_text() + "\n"
                    curr = nxt

        # 1〜2桁の数字を抽出
        raw_numbers = re.findall(r"\b\d{1,2}\b", target_text)
        max_num = (
            31
            if loto_type == "ミニロト"
            else (43 if loto_type == "ロト6" else 37)
        )

        # 「第1300回」や「24個以内」などの文章ノイズを除外
        noise_matches = re.findall(r"(\d+)(?:回|個|月|日|%)", target_text)
        noise_set = set(int(n) for n in noise_matches)

        new_numbers = []
        for n_str in raw_numbers:
            n = int(n_str)
            if 1 <= n <= max_num and n not in noise_set:
                if n not in new_numbers:
                    new_numbers.append(n)
        new_numbers.sort()

        # 最低限の数字が取れなかった場合はエラーとする（サイト構造変化の検知）
        if len(new_numbers) < 5:
            raise Exception("有効な予想数字エリアから数字を抽出できませんでした。")

        # 4. 【CSV更新判定】古いデータと比較して、更新があった場合のみ保存
        has_changed = True
        if os.path.exists(csv_filename):
            df_old = pd.read_csv(csv_filename)
            old_numbers = df_old["numbers"].tolist()
            if old_numbers == new_numbers:
                has_changed = False  # 内容が全く同じなら更新フラグを倒す

        if has_changed:
            # 新しい数字でCSVを上書きアップデート
            df_new = pd.DataFrame({"numbers": new_numbers})
            df_new.to_csv(csv_filename, index=False)
            msg = f"🎉 管理サイトの更新を検知！最新のビアス式数字（{len(new_numbers)}個）でCSVをアップデートしました。"
        else:
            msg = "ℹ️ サイトを確認しましたが、ビアス式数字に更新はありませんでした（データ維持）。"

        # 5. 【ログ記録】確認が終わったので、今日の確認ログを残す
        with open(check_log_file, "w", encoding="utf-8") as f:
            f.write(today_str)

        return new_numbers, msg

    except Exception as e:
        # 通信エラーや解析失敗時は、既存のCSV（過去のキャッシュ）があれば救済措置としてそれを返す
        if os.path.exists(csv_filename):
            df_cache = pd.read_csv(csv_filename)
            return (
                df_cache["numbers"].tolist(),
                f"⚠️ サイト接続失敗のため、前回保存されたCSVからデータを読み込みました。({e})",
            )
        return None, f"❌ 自動更新エラー（過去のCSVデータも存在しません）: {e}"
