from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from main import verify_token

router = APIRouter()

class ChatRequest(BaseModel):
    question: str
    sensor_context: dict  # latest sensor readings sent from frontend

def build_system_prompt(ctx: dict) -> str:
    return f"""You are HiveAI, an expert beekeeping assistant analyzing a smart beehive.

Current sensor readings:
- Temperature: {ctx.get('temp_c', 'N/A')} °C
- Humidity: {ctx.get('humidity', 'N/A')} %
- Pressure: {ctx.get('pressure', 'N/A')} hPa
- Hive weight: {ctx.get('weight_kg', ctx.get('weight', 'N/A'))} kg
- Alcohol (MQ-3): {ctx.get('alcohol_ppm', 'N/A')} ppm
- Methane (MQ-4): {ctx.get('methane_ppm', 'N/A')} ppm
- Noise: {ctx.get('noise_db', 'N/A')} dB
- Day status: {ctx.get('status', 'unknown')}

Give practical, concise beekeeping advice based on these readings. Max 120 words."""

@router.post("/chat")
def chat(body: ChatRequest, username: str = Depends(verify_token)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI key not configured on server")

    client = OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": build_system_prompt(body.sensor_context)},
                {"role": "user",   "content": body.question}
            ],
            max_tokens=200,
            temperature=0.7
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        # Avoid leaking internal errors/config in production.
        if os.getenv("ENV", "development").lower() == "production":
            raise HTTPException(status_code=500, detail="Upstream AI request failed")
        raise HTTPException(status_code=500, detail=str(e))
