
"""
Asistente Operativo (stub) con FastAPI + RAG (skeleton)
- Endpoint /ask_ops que recibiría una pregunta y consultaría un índice local (FAISS)
- Este archivo NO construye el índice (eso lo harás con tus SOPs).
Requisitos:
    pip install fastapi uvicorn
Ejecutar:
    uvicorn rag_assistant_stub:app --reload --port 8000
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Ops Assistant (RAG Stub)")

class Ask(BaseModel):
    question: str

@app.get("/health")
def health():
    return {"status":"ok"}

@app.post("/ask_ops")
def ask_ops(payload: Ask):
    # Aquí deberías:
    # 1) Vectorizar la pregunta
    # 2) Consultar FAISS / índices locales de SOPs
    # 3) Combinar pasajes relevantes + plantilla de respuesta
    # 4) (Opcional) Pasar por un LLM local/externo para redacción final
    answer = (
        "Stub de respuesta.\n\n"
        "Para habilitar RAG: crea un índice con tus SOPs (PDF/MD/DOC), "
        "almacena embeddings (FAISS) y trae pasajes relevantes."
    )
    return {"answer": answer}
