import time, json, httpx
for date, venue in [("20260608", "芦屋"), ("20260611", "尼崎")]:
    payload = {"date": date, "venues": [venue], "items": ["results"], "secret": "boatrace-sakura-secret-2024"}
    t0 = time.time()
    try:
        with httpx.Client(timeout=300) as c:
            r = c.post("http://153.121.51.74:8080/scrape", json=payload)
        print(venue, date, r.status_code, round(time.time() - t0, 1), "s", json.dumps(r.json(), ensure_ascii=False)[:200])
    except Exception as e:
        print(venue, date, "ERR", e)
