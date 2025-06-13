from fastapi import FastAPI

app = FastAPI(title="Flux Real-Time City Data Intelligence Platform")

@app.get("/")
async def root():
    return {"message": "Welcome to Flux API"}

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Flux API is up and running!"}
