from fastapi import FastAPI

from routers.tracer import router as tracer_router

app = FastAPI(title="agent-trace", version="0.1.0")
app.include_router(tracer_router)
