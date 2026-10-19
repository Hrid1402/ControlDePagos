from fastapi import FastAPI

app = FastAPI(title="Control de Pagos")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
