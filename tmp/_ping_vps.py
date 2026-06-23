import httpx
for path in ["/", "/health"]:
    try:
        r = httpx.get("http://153.121.51.74:8080" + path, timeout=15)
        print(path, r.status_code, r.text[:200])
    except Exception as e:
        print(path, "ERR", e)
