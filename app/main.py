import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
