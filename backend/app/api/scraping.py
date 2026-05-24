from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel
from backend.app.scrapers.boaters import scrape_venues, scrape_race_entry
from backend.app.scrapers.boatfrontier import scrape_motor_data
from backend.app.scrapers.exhibition import scrape_exhibition_data

router = APIRouter()

VENUE_LIST = [
    "桐生", "戸田", "江戸川", "平和島", "多摩川", "浜名湖",
    "蒲郡", "常滑", "津", "三国", "びわこ", "住之江",
    "尼崎", "鳴門", "丸亀", "児島", "宮島", "徳山",
    "下関", "若松", "芦屋", "福岡", "唐津", "大村"
]


class ScrapeRequest(BaseModel):
    date: str
    venues: List[str]
    items: List[str]  # "entry", "motor", "exhibition"


@router.get("/venues")
async def get_venues():
    return {"venues": VENUE_LIST}


@router.post("/run")
async def run_scraping(req: ScrapeRequest):
    results = []

    for venue in req.venues:
        for item in req.items:
            try:
                if item == "entry":
                    await scrape_race_entry(venue, req.date)
                    results.append({"venue": venue, "item": item, "status": "ok"})
                elif item == "motor":
                    await scrape_motor_data(venue, req.date)
                    results.append({"venue": venue, "item": item, "status": "ok"})
                elif item == "exhibition":
                    await scrape_exhibition_data(venue, req.date)
                    results.append({"venue": venue, "item": item, "status": "ok"})
                else:
                    results.append({"venue": venue, "item": item, "status": "error", "message": f"Unknown item: {item}"})
            except Exception as e:
                results.append({"venue": venue, "item": item, "status": "error", "message": str(e)})

    return {"results": results}
