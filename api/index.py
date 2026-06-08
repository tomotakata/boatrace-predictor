import sys
sys.path.insert(0, "/var/task")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

app = FastAPI(title="Boatrace Predictor API", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.app.api.races import router as races_router
    from backend.app.api.analytics import router as analytics_router
    from backend.app.api.scraping import router as scraping_router
    from backend.app.api.venues import router as venues_router

    app.include_router(races_router, prefix="/api/races", tags=["races"])
    app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(scraping_router, prefix="/api/scrape", tags=["scraping"])
    app.include_router(venues_router, prefix="/api/venues", tags=["venues"])
except Exception as e:
    @app.get("/api/health")
    async def health():
        return {"status": "error", "detail": str(e)}


@app.get("/api/")
async def root():
    routes = [r.path for r in app.routes if hasattr(r, 'path')]
    scrape_routes = [r for r in routes if 'scrape' in r]
    return {"message": "Boatrace Predictor API v1.1", "scrape_routes": scrape_routes}


handler = Mangum(app, lifespan="off")
