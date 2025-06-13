# ollama_advisor.py
import json
import httpx

# Configuration for Ollama
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:1b" 

async def get_ollama_action(human_command: str, telemetry_data: dict):
    prompt_content = f"""
    You are an AI drone mission planner and safety monitor. Your primary goal is to respond to user commands
    and maintain drone safety, providing structured MAVSDK-compatible actions.

    The drone's current telemetry is:
    {json.dumps(telemetry_data, indent=2)}

    The human command is: "{human_command}"

    Based on the human command and current telemetry, you must output a single JSON object.
    This JSON object should represent the next logical action the drone should take or a critical safety directive.

    Here are the possible JSON action formats you can return:

    1.  **Takeoff:**
        {{ "action": "takeoff", "altitude_m": <float> }}
        (Only if drone is on ground and not armed)

    2.  **Goto Location:**
        {{ "action": "goto", "latitude_deg": <float>, "longitude_deg": <float>, "altitude_m": <float> }}
        (Only if drone is armed and in air, and global_position_ok is True)

    3.  **Land:**
        {{ "action": "land" }}
        (Only if drone is armed and in air)

    4.  **Return to Launch (RTL):**
        {{ "action": "rtl" }}
        (Only if drone is armed and in air, and home_position_ok is True)

    5.  **Arm:**
        {{ "action": "arm" }}
        (Only if drone is not armed, not in air, and health.armable is True)

    6.  **Disarm:**
        {{ "action": "disarm" }}
        (Only if drone is armed and not in air, generally for post-landing)

    7.  **Hold/Do Nothing:**
        {{ "action": "hold", "reason": "No immediate action needed or waiting for conditions." }}
        (Use this if no specific action is required or if conditions are not met for other actions)

    8.  **Error/Human Intervention:**
        {{ "action": "error", "message": "Description of why an action cannot be performed or a critical unresolvable issue." }}
        (Use this for unrecoverable errors or when human input is absolutely required)

    Consider these safety and operational rules:
    - If battery remaining is below 15% AND drone is in_air, suggest 'rtl' if home_position_ok, else 'land'.
    - If GPS fix type is 0 (No Fix) AND drone is in_air, suggest 'land'.
    - If GPS fix type is 1 (No GPS) AND drone is in_air, suggest 'land'.
    - If health.armable is False AND drone is not armed and not in_air, suggest 'error' with message 'Pre-arm checks failed'.
    - If drone is not armed and not in_air, and the human command implies flight, suggest 'arm' then 'takeoff'.
    - Always prioritize safety actions (land, rtl) if conditions are critical.

    Output only the JSON. Do not include any other text or markdown fences.
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

