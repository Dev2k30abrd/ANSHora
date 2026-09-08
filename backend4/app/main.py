from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.dataset import router as dataset_router
from app.routes.analytics import router as analytics_router
from app.routes.agent import router as agent_router


app = FastAPI(
    title="DataMind Analyst API",
    description="Backend for the AI senior-data-analyst agent",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dataset_router)
app.include_router(analytics_router)
app.include_router(agent_router)


@app.get("/")
def root():
    return {"message": "DataMind Analyst API is running", "version": "0.2.0"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
