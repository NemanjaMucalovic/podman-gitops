import logging
from fastapi import FastAPI
from uvicorn import run

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Podman GitOps",
    description="A lightweight GitOps tool for managing Podman container deployments",
    version="0.1.0"
)

@app.get("/")
async def root():
    return {"message": "Podman GitOps API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

def main():
    """Main entry point for the application."""
    logger.info("Starting Podman GitOps service")
    run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main() 