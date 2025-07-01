# ollama_advisor.py
import json
import httpx
import asyncio

# Configuration for Ollama
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "deepseek-r1:1.5b" 

async def get_ollama_action(mission_statement: str):
    prompt_content = f"""
You are a highly accurate Drone Mission Planner AI.

Your task is to convert the given mission statement (written in simple natural language) into a step-by-step list of **structured micro steps** for the drone.

You are limited to using only **three actions**:
- `"takeoff"` — with a specified altitude in meters.
- `"goto"` — move relative to the current position with directions in meters (north/south, east/west) and maintain a specified altitude.
- `"land"` — end the mission.

### Response Format Rules:
- Respond in **valid JSON only**.
- Do **not include any extra text**, explanations, or comments.
- Each step must have a key like `"step 1"`, `"step 2"`, etc.
- The value is a string describing the action and parameters.

### Example JSON Format:
```json
{
  "step 1": "takeoff to 20m",
  "step 2": "goto north 5m, east -10m, altitude 20m",
  "step 3": "goto north 10m, east -5m, altitude 30m",
  "step 4": "land"
}

here is the mission statement you have to work on {mission_statement}.

"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt_content,
        "stream": False,
        "format": "json" 
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60.0) # Increased timeout
            response.raise_for_status()
            
            raw_text = response.json().get("response", "").strip()
            
            # Attempt to parse the raw text as JSON, cleaning up potential markdown fences
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            parsed_json = json.loads(clean_text)
            return parsed_json

    except json.JSONDecodeError as e:
        print(f"JSON parsing error from Ollama: {e}")
        print(f"Ollama Raw Text (for debugging):\n{raw_text}")
        return {"action": "error", "message": f"LLM response not valid JSON: {e}"}
    except httpx.RequestError as e:
        print(f"Ollama connection error: {e}")
        return {"action": "error", "message": f"Ollama connection failed: {e}"}
    except httpx.HTTPStatusError as e:
        print(f"Ollama API error: {e.response.status_code} - {e.response.text}")
        return {"action": "error", "message": f"Ollama API error {e.response.status_code}"}
    except Exception as e:
        print(f"An unexpected error occurred with Ollama: {e}")
        return {"action": "error", "message": f"Unexpected LLM issue: {e}"}



async def main_ollama_test():
    testcases = [
       " takeoff at 20m  then move 10 in north, then move 10m in east and then land."
       "takeoff at 10m and inspect reagion in 10m radius."
    ]
    
    for t in testcases:
        print(f"Testing Ollama -> {t}:")
        llm_output = await get_ollama_action(t)
        print(json.dumps(llm_output, indent=2))
    
    
    

if __name__ == "__main__":
    asyncio.run(main_ollama_test())