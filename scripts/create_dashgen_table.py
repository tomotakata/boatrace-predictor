#!/usr/bin/env python3
"""
dashgen_results テーブルを Supabase に作成するマイグレーションスクリプト

さくらサーバーの /migrate エンドポイントを呼び出して
dashgen_results テーブルを作成する。
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass


SAKURA_URL = os.getenv("SAKURA_SCRAPER_URL", "http://153.121.51.74:8080")
SAKURA_SECRET = os.getenv("SAKURA_SCRAPER_SECRET", "boatrace-sakura-secret-2024")


def main():
    print(f"Calling Sakura server migrate endpoint: {SAKURA_URL}/migrate")

    data = json.dumps({"secret": SAKURA_SECRET}).encode("utf-8")
    req = urllib.request.Request(
        f"{SAKURA_URL}/migrate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read().decode())
        print(f"Status: {body.get('status')}")
        print(f"Message: {body.get('message')}")
        if body.get("status") == "ok":
            print("Migration completed successfully!")
        else:
            print("Migration returned non-ok status")
            if body.get("manual_migration_sql"):
                print("\nManual SQL:")
                print(body["manual_migration_sql"])
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Verify table exists via Supabase REST API
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if url and key:
        try:
            from supabase import create_client
            sb = create_client(url, key)
            r = sb.table("dashgen_results").select("count", count="exact").limit(0).execute()
            print(f"\nVerification: dashgen_results table exists, count={r.count}")
        except Exception as e:
            print(f"\nVerification failed: {e}")
            print("The table may not have been created. Check the Sakura server logs.")


if __name__ == "__main__":
    main()
