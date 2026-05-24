import sys
sys.path.insert(0, "/var/task")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

app = FastAPI(title="Boatrace Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import routers
try:
    from backend.app.api.races import router as races_router
    from backend.app.api.analytics import router as analytics_router
    from backend.app.api.scraping import router as scraping_router

    app.include_router(races_router, prefix="/races", tags=["races"])
    app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
    app.include_router(scraping_router, prefix="/scrape", tags=["scraping"])
except Exception as e:
    @app.get("/health")
    async def health():
        return {"status": "error", "detail": str(e)}


@app.get("/")
async def root():
    return {"message": "Boatrace Predictor API v1.0"}


handler = Mangum(app, lifespan="off")
