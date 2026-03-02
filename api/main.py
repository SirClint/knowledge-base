from fastapi import FastAPI

app = FastAPI(title="Knowledge Base API")


@app.get("/health")
async def health():
    return {"status": "ok"}
