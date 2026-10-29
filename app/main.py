import os

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.skill_match import router as skill_match_router

app = FastAPI(
    title="RADIX Talent Match — Role 5: Skill Matching API",
    description=(
        "Production-grade Skill Matching Engine for the RADIX Talent Match Hackathon. "
        "Deterministically evaluates candidate profiles from Role 3 against job requirements "
        "from Role 1 with factual, explainable justifications."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Role 1, Role 3, and the candidate portal are separate browser clients in
# development.  Permit their cross-origin JSON requests by default, while
# allowing a deployment to restrict this with ALLOWED_ORIGINS.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Register routers
app.include_router(skill_match_router)


@app.get(
    "/",
    tags=["Root"],
    summary="Service Index",
    response_description="Basic service information and status",
)
def root():
    return {
        "service": "RADIX Talent Match — Role 5: Skill Matching API",
        "version": "1.0.0",
        "status": "running",
        "docs_url": "/docs",
        "endpoints": {
            "health": "/health",
            "skill_match": "/api/v1/skill-match",
        },
    }


@app.get(
    "/health",
    tags=["System"],
    summary="Health Check",
    response_description="Returns the health status of the service",
)
def health_check():
    return {
        "status": "healthy",
        "service": "radix-role5",
        "version": "1.0.0",
    }


@app.get(
    "/api/v1/health",
    tags=["System"],
    summary="API Health Check",
    include_in_schema=False,
)
def api_health_check():
    """Compatibility health route for API gateways that probe under /api/v1."""
    return health_check()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Returns clean, client-friendly validation errors without leaking sensitive stack details.
    """
    errors = []
    for err in exc.errors():
        field_loc = " -> ".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "Invalid field")
        errors.append(f"{field_loc}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": "Validation Error",
            "message": "The request payload failed schema validation.",
            "details": errors,
        },
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        # Cloud hosts inject PORT and require the process to listen publicly.
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENVIRONMENT", "").lower() == "development",
    )
