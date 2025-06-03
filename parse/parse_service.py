import json, os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from llama_cpp import Llama  # cpu-only ok

MODEL_PATH = os.getenv("MODEL_PATH", "/models/llama-3-8b-instruct.Q4_K_M.gguf")
llm = Llama(model_path=MODEL_PATH, n_ctx=2048)
app = FastAPI()

class Transcript(BaseModel):
    text: str
    sender: str

SYSTEM_MSG = (
    "You are an extraction engine. Return only valid JSON with keys:\n"
    "desired_model, intent_window_days, test_drive_flag, test_drive_score,\n"
    "stock_flag, financing_flag, objection_codes, outcome, competitor_brand,\n"
    "salesperson_id. Use null for unknown. Do NOT explain."
)

@app.post("/parse")
def parse(t: Transcript):
    prompt = f"{SYSTEM_MSG}\n\nTranscript: {t.text}\nJSON:"
    out = llm(prompt, max_tokens=512, stop=["```"])
    try:
        js = json.loads(out["choices"][0]["text"].strip())
    except json.JSONDecodeError:
        raise HTTPException(422, "LLM returned invalid JSON")
    return js

