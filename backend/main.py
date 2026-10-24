import os
import json
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import uvicorn

from app.api.routes import router
from app.models.database import engine, Base
from app.models import Task, User, Conversation, ConversationMessage, ServiceConfig

# Load environment variables
load_dotenv()

# Create the log directory before configuring FileHandler. Without this,
# importing the application from a clean checkout can fail on startup.
os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/ai_orchestrator.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting AI Orchestrator application...")
    
    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
    
    # Initialize default service configurations
    try:
        from sqlalchemy.orm import Session
        db = Session(engine)
        
        # Check if service configs exist, if not create defaults
        existing_configs = db.query(ServiceConfig).count()
        if existing_configs == 0:
            default_configs = [
                ServiceConfig(
                    service_name="browser_service",
                    service_type="browser",
                    base_url=os.getenv("BROWSER_SERVICE_URL", "http://localhost:8001"),
                    is_active=True,
                    endpoints={"execute": "/execute", "health": "/health"}
                ),
                ServiceConfig(
                    service_name="document_service",
                    service_type="document",
                    base_url=os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8002"),
                    is_active=True,
                    endpoints={"process": "/process", "health": "/health"}
                ),
                ServiceConfig(
                    service_name="communication_service",
                    service_type="communication",
                    base_url=os.getenv("COMMUNICATION_SERVICE_URL", "http://localhost:8003"),
                    is_active=True,
                    endpoints={"handle": "/handle", "health": "/health"}
                ),
                ServiceConfig(
                    service_name="media_service",
                    service_type="media",
                    base_url=os.getenv("MEDIA_SERVICE_URL", "http://localhost:8004"),
                    is_active=True,
                    endpoints={"process": "/process", "health": "/health"}
                ),
                ServiceConfig(
                    service_name="bot_builder_service",
                    service_type="bot_builder",
                    base_url=os.getenv("BOT_BUILDER_SERVICE_URL", "http://localhost:8005"),
                    is_active=True,
                    endpoints={"create": "/create", "health": "/health"}
                )
            ]
            
            for config in default_configs:
                db.add(config)
            db.commit()
            logger.info("Default service configurations created")
        
        db.close()
        
    except Exception as e:
        logger.error(f"Error initializing service configurations: {e}")
    
    logger.info("AI Orchestrator application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Orchestrator application...")

# Create FastAPI app
app = FastAPI(
    title="AI Orchestrator",
    description="A comprehensive AI-powered orchestration platform that manages multiple services through natural language commands.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Restrict browser access to configured frontend origins. CORS is not an
# authentication mechanism; keep the API on a trusted network until auth exists.
_raw_cors_origins = os.getenv(
    "CORS_ORIGINS",
    '["http://localhost:3000", "http://localhost:8000"]',
)
try:
    _parsed_cors_origins = json.loads(_raw_cors_origins)
    if not isinstance(_parsed_cors_origins, list):
        raise ValueError("CORS_ORIGINS must be a JSON list or comma-separated origins")
except json.JSONDecodeError:
    _parsed_cors_origins = _raw_cors_origins.split(",")

CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in _parsed_cors_origins
    if isinstance(origin, str) and origin.strip()
]
if not CORS_ORIGINS or "*" in CORS_ORIGINS:
    raise ValueError("CORS_ORIGINS must contain explicit origins; wildcard origins are not supported")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Keep details in server logs, but do not return internal exception text to clients.
    logger.exception("Unhandled request error")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Include API routes
app.include_router(router, prefix="/api/v1", tags=["AI Orchestrator"])

# Resolve frontend assets relative to this file, not the current working directory.
STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend" / "static"
INDEX_FILE = STATIC_DIR / "index.html"

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    if INDEX_FILE.is_file():
        return FileResponse(str(INDEX_FILE))
    return {
        "message": "AI Orchestrator API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
        "note": "Frontend assets are not included in this deployment."
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "AI Orchestrator is running",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("DEBUG", "False").lower() == "true"
    
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )