import os
import logging
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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler caught: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "message": str(exc)}
    )

# Include API routes
app.include_router(router, prefix="/api/v1", tags=["AI Orchestrator"])

# Serve static files from frontend directory
try:
    app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")
except:
    # If frontend/static doesn't exist, create a simple fallback
    pass

# Root endpoint - serve the main HTML file
@app.get("/")
async def root():
    try:
        return FileResponse("../frontend/static/index.html")
    except:
        # Fallback if frontend files don't exist
        return {
            "message": "AI Orchestrator API",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
            "redoc": "/redoc",
            "note": "Frontend files not found. Please build the frontend first."
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