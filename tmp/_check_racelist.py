import httpx
from bs4 import BeautifulSoup
cases = [
    ("20260606","19","下関"),
    ("20260606","04","平和島"),
    ("20260608","02","戸田"),
    ("20260506","19","下関"),  # 取得成功した古い日付(比較用)
]
for hd, jcd, name in cases:
    url=f"https://www.boatrace.jp/owpc/pc/race/racelist?hd={hd}&jcd={jcd}&rno=1"
    try:
        r=httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"})
        soup=BeautifulSoup(r.text,"html.parser")
        rows=soup.select("table tbody tr")
        # 結果ページへのリダイレクト/「該当する出走表はありません」検出
        body_txt=soup.get_text()[:0]
        has_no=("出走表はありません" in r.text) or ("ありません" in r.text)
        print(f"{name} {hd}: status={r.status_code} tbody_tr={len(rows)} no_msg={has_no} final_url={str(r.url)[-60:]}")
    except Exception as e:
        print(f"{name} {hd}: ERR {e}")
