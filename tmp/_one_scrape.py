import time, json, httpx
payload = {"date":"20260606","venues":["丸亀"],"items":["results"],"secret":"boatrace-sakura-secret-2024"}
t0=time.time()
try:
    with httpx.Client(timeout=600) as c:
        r=c.post("http://153.121.51.74:8080/scrape", json=payload)
    dt=time.time()-t0
    print("status", r.status_code, "elapsed", round(dt,1),"s")
    print(json.dumps(r.json(), ensure_ascii=False)[:600])
except Exception as e:
    print("ERR", round(time.time()-t0,1),"s", e)
