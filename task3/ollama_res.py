# ollama_advisor.py
import json
import httpx
import asyncio

# Configuration for Ollama
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "deepseek-r1:1.5b" 

async def get_ollama_action(mission_statement: str, telemetry_data: dict):
    prompt_content = f"""
You are an AI drone controller. You are provided with the mission and current state of the Drone provide next micro step in order to complete mission.

**Telemetry:**
{json.dumps(telemetry_data, indent=2)}

**Mission Statement:** "{mission_statement}"

**Output ONLY a single JSON object with "action" and optional parameters.
Set parameters to `null` if not applicable to the action.**

**Available Actions & Parameters:**
* `takeoff`: {{"action": "takeoff", "altitude_m": <float>}}
* `arm`: {{"action": "arm", "latitude": null, "longitude": null, "altitude_m": null}}
* `disarm`: {{"action": "disarm", "latitude": null, "longitude": null, "altitude_m": null}}
* `goto`: {{"action": "goto", "latitude": <float>, "longitude": <float>, "altitude_m": <float>}}
* `rtl`: {{"action": "rtl", "latitude": null, "longitude": null, "altitude_m": null}}
* `land`: {{"action": "land", "latitude": null, "longitude": null, "altitude_m": null}}
* `hold`: {{"action": "hold", "latitude": null, "longitude": null, "altitude_m": null}}
* `nothing`: {{"action": "nothing", "latitude": null, "longitude": null, "altitude_m": null}}

**Consider state transitions and safety:**
- Arm before takeoff.
- Land before disarm.
- Prioritize RTL/land for low battery or GPS loss.
- Suggest "hold" or "nothing" if waiting or busy.
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
        {
            "test_type": "lowBattery",
            "human_response": "go to latitude 25, longitude 48, at 30 altitude",
            "telemetry": {
                "position": {"latitude_deg": 23.0225, "longitude_deg": 72.5714, "relative_altitude_m": 30.0},
                "velocity_ned": {"north_m_s": 5.0, "east_m_s": 0.0, "down_m_s": 0.0},
                "attitude_euler": {"roll_deg": 2.0, "pitch_deg": 1.0, "yaw_deg": 90.0},
                "battery": {"remaining_percent": 12, "voltage_v": 22.1},
                "flight_mode": "AUTO",
                "gps_info": {"num_satellites": 12, "fix_type": 3},
                "in_air": True,
                "armed": True
            }
        },
        {
            "test_type": "goTo",
            "human_response": "go to latitude 25, longitude 48, at 30 altitude",
            "telemetry": {
                "position": {"latitude_deg": 23.0225, "longitude_deg": 72.5714, "relative_altitude_m": 30.0},
                "velocity_ned": {"north_m_s": 0.0, "east_m_s": 0.0, "down_m_s": 0.0},
                "attitude_euler": {"roll_deg": 2.0, "pitch_deg": 1.0, "yaw_deg": 90.0},
                "battery": {"remaining_percent": 93, "voltage_v": 22.1},
                "flight_mode": "AUTO",
                "gps_info": {"num_satellites": 12, "fix_type": 3},
                "in_air": False,
                "armed": False
            }
        }
    ]
    
    for t in testcases:
        print(f"Testing Ollama {t['test_type']}:")
        llm_output = await get_ollama_action(t['human_response'], t['telemetry'])
        print(json.dumps(llm_output, indent=2))
    
    
    

if __name__ == "__main__":
    asyncio.run(main_ollama_test())