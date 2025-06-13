
import json
import asyncio
import httpx 

# Configuration for Ollama
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:1b" 

async def get_ollama_response(telemetry_data: dict):    
    prompt_content = f"""
    You are an AI assistant for a drone operation. Your task is to analyze the provided drone telemetry data,
    identify any issues or notable statuses, provide a human-readable summary, and suggest a proactive action if necessary.

    Here is the current drone telemetry data in JSON format:
    {json.dumps(telemetry_data, indent=2)}

    Based on this data, please provide your analysis in the following structured JSON format:
    {{
        "summary": "A concise human-readable summary of the drone's status, highlighting any critical issues.",
        "issues_detected": [
            "Issue 1 description (e.g., 'Low battery')",
            "Issue 2 description (e.g., 'GPS signal lost')"
        ],
        "suggested_action": "A single, clear, proactive action for the drone operator or the drone itself (e.g., 'Return to home', 'Land immediately', 'Continue mission', 'Check GPS module'). If no immediate action is needed, state 'Monitor'."
    }}
    
    Consider the following rules for suggestions:
    - If battery remaining is below 15%, suggest 'Initiate Return to Launch (RTL)'.
    - If GPS fix type is 0 (No Fix) and drone is in_air, suggest 'Land immediately and check GPS'.
    - If GPS fix type is 1 (No GPS) and drone is in_air, suggest 'Consider landing, GPS degraded'.
    - If health.armed is False but in_air is True, suggest 'Investigate unexpected disarm'.
    - If health.armable is False and drone is not armed and not in_air, suggest 'Check pre-arm checks'.
    - If no critical issues, suggest 'Continue mission'.
    - Ensure your response is ONLY the JSON object, without any leading or trailing text like markdown fences.
    """

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt_content,
        "stream": False, 
        "format": "json" 
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=30.0)
            response.raise_for_status() 
            
            response_data = response.json()
            
        
            raw_text = response_data.get("response", "").strip()
            
            # Attempt to parse the raw text as JSON
            try:
                # Remove common markdown fences if present
                clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                parsed_json = json.loads(clean_text)
                return parsed_json
            except json.JSONDecodeError as e:
                print(f"JSON parsing error from Ollama: {e}")
                print(f"Ollama Raw Text (for debugging):\n{raw_text}")
                return {
                    "summary": "Error: Ollama response not valid JSON.",
                    "issues_detected": ["LLM parsing error"],
                    "suggested_action": "Request human intervention"
                }

    except httpx.RequestError as e:
        print(f"Ollama connection error: {e}")
        return {
            "summary": "Error: Could not connect to Ollama.",
            "issues_detected": ["Ollama connection failed"],
            "suggested_action": "Check Ollama server status"
        }
    except httpx.HTTPStatusError as e:
        print(f"Ollama API error: {e.response.status_code} - {e.response.text}")
        return {
            "summary": "Error: Ollama API returned an error.",
            "issues_detected": [f"Ollama API error {e.response.status_code}"],
            "suggested_action": "Check Ollama logs"
        }
    except Exception as e:
        print(f"An unexpected error occurred with Ollama: {e}")
        return {
            "summary": "Error: Unexpected LLM issue.",
            "issues_detected": ["Unexpected LLM error"],
            "suggested_action": "Request human intervention"
        }

# Example usage (for testing this module independently)
async def main_ollama_test():
    test_telemetry_low_battery = {
        "position": {"latitude_deg": 23.0225, "longitude_deg": 72.5714, "relative_altitude_m": 30.0},
        "velocity_ned": {"north_m_s": 5.0, "east_m_s": 0.0, "down_m_s": 0.0},
        "attitude_euler": {"roll_deg": 2.0, "pitch_deg": 1.0, "yaw_deg": 90.0},
        "battery": {"remaining_percent": 12, "voltage_v": 22.1}, 
        "flight_mode": "AUTO",
        "gps_info": {"num_satellites": 12, "fix_type": 3},
        "in_air": True,
        "armed": True
    }
    
    print("Testing Ollama with low battery telemetry:")
    llm_output = await get_ollama_response(test_telemetry_low_battery)
    print(json.dumps(llm_output, indent=2))

if __name__ == "__main__":
    asyncio.run(main_ollama_test())