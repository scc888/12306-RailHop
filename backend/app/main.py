"""
FastAPI 主服务入口
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .api.routes import router
from .services.station_service import station_service
from .services.client_12306 import client_12306

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("12306_tool")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务启动预热
    logger.info("Starting up 12306 Tool Backend Service...")
    try:
        station_service.ensure_loaded()
        client_12306.ensure_init()
        logger.info(f"Preloaded {len(station_service.stations)} stations into memory.")
    except Exception as e:
        logger.error(f"Error during startup preheat: {e}")
    yield
    logger.info("Shutting down 12306 Tool Backend Service...")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# 允许跨域请求以供前端联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def index():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "status": "online"
    }

@app.get("/health")
def health():
    station_service.ensure_loaded()
    return {
        "status": "healthy",
        "stations_loaded": len(station_service.stations)
    }
