from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.races import router as races_router
from backend.app.api.analytics import router as analytics_router
from backend.app.api.scraping import router as scraping_router
from backend.app.api.venues import router as venues_router

app = FastAPI(title="Boatrace Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(races_router, prefix="/races", tags=["races"])
app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
app.include_router(scraping_router, prefix="/scrape", tags=["scraping"])
app.include_router(venues_router, prefix="/venues", tags=["venues"])

@app.get("/")
async def root():
    return {"message": "Boatrace Predictor API"}
