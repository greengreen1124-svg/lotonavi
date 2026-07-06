import os
import re
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup

URL = "http://sougaku.com/loto7/index.html"
CSV_FILE = "loto7_history.csv"
PICK_NUM = 7
BONUS_NUM = 2
TOTAL_NUM = PICK_NUM + BONUS_NUM

def fetch_latest_result():
    try:
        res = requests.get(URL, timeout=10)
        res.encoding = res.apparent_encoding if res.apparent_encoding else 'utf-8'
        soup = BeautifulSoup(res.text, "html.parser")
        
        target_tr = None
        for tr in soup.find_all("tr"):
            text = tr.get_text()
            if "抽選回" in text and "抽選日" in text and "本数字" in text:
                target_tr = tr.find_next_sibling("tr")
                break
                
        if not target_tr:
            print("❌ 見出しの直下からデータ行を特定できませんでした。")
            return None
            
        cells = [c.get_text().strip() for c in target_tr.find_all(["td", "th"])]
        joined_text = " ".join(cells)
        
        round_num = None
        for c in cells:
            r_match = re.search(r"第?(\d+)回", c)
            if r_match:
                round_num = int(r_match.group(1))
                break
                
        date_str = None
        for c in cells:
            d_match = re.search(r"(\d{4}|\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", c)
            if d_match:
                year = d_match.group(1)
                if len(year) == 2: year = "20" + year
                date_str = f"{year}/{int(d_match.group(2)):02d}/{int(d_match.group(3)):02d}"
                break
                
        set_ball = "A"
        for c in cells:
            s_match = re.search(r"\b([A-J])\b|([A-J])セット|([A-J])球", c.upper())
            if s_match:
                set_ball = [g for g in s_match.groups() if g][0]
                break
                
        pure_numbers = []
        for c in cells:
            if any(k in c for k in ["回", "年", "/", "-", "セット"]) or c.upper() in list("ABCDEFGHIJ"):
                continue
            ns = [int(n) for n in re.findall(r"\d+", c)]
            if 0 < len(ns) <= 9:
                pure_numbers.extend(ns)
                
        if len(pure_numbers) < TOTAL_NUM:
            all_digits = [int(n) for n in re.findall(r"\d+", joined_text)]
            if len(all_digits) >= TOTAL_NUM:
                pure_numbers = all_digits[-TOTAL_NUM:]
                
        if not round_num or len(pure_numbers) < TOTAL_NUM:
            print("❌ データの解析に失敗しました。")
            return None
            
        return {
            "round": round_num,
            "date": date_str if date_str else "2026/01/01",
            "numbers": pure_numbers[:PICK_NUM],
            "bonuses": pure_numbers[PICK_NUM:TOTAL_NUM],
            "set": set_ball
        }
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return None

def main():
    if not os.path.exists(CSV_FILE):
        print(f"❌ `{CSV_FILE}` が見つかりません。")
        return
        
    result = fetch_latest_result()
    if not result:
        return
        
    df = pd.read_csv(CSV_FILE)
    if result["round"] in df["開催回"].values:
        print(f"ℹ️ 第 {result['round']} 回の結果は既にCSVに存在するためスキップします。")
        return
        
    new_row = {"開催回": result["round"], "日付": result["date"]}
    for i, num in enumerate(result["numbers"], 1):
        new_row[f"第{i}数字"] = num
        
    cols = df.columns.tolist()
    if "BONUS数字1" in cols and len(result["bonuses"]) > 0:
        new_row["BONUS数字1"] = result["bonuses"][0]
    if "BONUS数字2" in cols and len(result["bonuses"]) > 1:
        new_row["BONUS数字2"] = result["bonuses"][1]
        
    if "セット" in cols:
        new_row["セット"] = result["set"]
        
    new_df = pd.DataFrame([new_row])
    for c in cols:
        if c not in new_df.columns:
            new_df[c] = np.nan
    new_df = new_df[cols]
    
    updated_df = pd.concat([df, new_df], ignore_index=True)
    updated_df.to_csv(CSV_FILE, index=False, encoding="utf-8")
    print(f"🎉 第 {result['round']} 回の結果を `{CSV_FILE}` に自動追加しました！")

if __name__ == "__main__":
    main()
