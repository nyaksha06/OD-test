# ollama_advisor.py
import json
import httpx
import asyncio

# Configuration for Ollama
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:1b" 

async def get_ollama_action(human_command: str, telemetry_data: dict):
    prompt_content ={
        "prompt1" :  f"""
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
    """ ,


    "prompt2" : f"""
You are an **AI drone mission controller and safety guardian**. Your sole purpose is to process the drone's current state and a human command, then issue the single, safest, and most logical drone action in **MAVSDK-compatible JSON format**.

---
**Current Drone Telemetry:**
{json.dumps(telemetry_data, indent=2)}

---
**Human Command:**
"{human_command}"

---
**Strict Operational Rules (Evaluate in Order of Priority):**

1.  **CRITICAL SAFETY FIRST:**
    * **Low Battery:** If `telemetry_data.battery.remaining_percent` is below 15% AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is True:
        * If `telemetry_data.health.home_position_ok` is True, command: `{{ "action": "rtl" }}`
        * Else (no home position), command: `{{ "action": "land" }}`
    * **GPS Loss (In Air):** If `telemetry_data.gps_info.fix_type` is 0 (No Fix) or 1 (No GPS) AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is True:
        * Command: `{{ "action": "land" }}`
    * **Pre-Arm Checks Failed (Cannot Arm/Fly):** If `telemetry_data.armed` is False AND `telemetry_data.in_air` is False AND `telemetry_data.health.armable` is False:
        * Command: `{{ "action": "error", "message": "Pre-arm checks failed. Cannot arm drone. Human intervention required." }}`

2.  **Human Command Fulfillment & State Management:**
    * **Arming for Flight:** If the `human_command` clearly implies flight (e.g., "take off", "fly", "go to", "start mission") AND `telemetry_data.armed` is False AND `telemetry_data.in_air` is False AND `telemetry_data.health.armable` is True:
        * Command: `{{ "action": "arm" }}` (The LLM will then be prompted again with the new state, where it can then trigger takeoff).
    * **Takeoff:** If `human_command` is "take off" or similar, AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is False AND `telemetry_data.on_ground` is True:
        * Command: `{{ "action": "takeoff", "altitude_m": <float, default 3.0> }}` (Choose a reasonable default if not specified in command, e.g., 3m)
    * **Go to Location:** If `human_command` includes a target location (e.g., "go to 12.34, 67.89 at 10m", "fly to building X") AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is True AND `telemetry_data.health.global_position_ok` is True:
        * Command: `{{ "action": "goto", "latitude_deg": <float>, "longitude_deg": <float>, "altitude_m": <float> }}` (Extract coordinates and altitude from command)
    * **Land:** If `human_command` is "land" or similar, AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is True:
        * Command: `{{ "action": "land" }}`
    * **Return to Launch (RTL):** If `human_command` is "return to launch" or "rtl", AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is True AND `telemetry_data.health.home_position_ok` is True:
        * Command: `{{ "action": "rtl" }}`
    * **Disarm:** If `human_command` is "disarm" AND `telemetry_data.armed` is True AND `telemetry_data.in_air` is False:
        * Command: `{{ "action": "disarm" }}`

3.  **Default/Fallback Actions:**
    * **Hold/No Immediate Action:** If the human command is unclear, or no other rule applies, or the conditions for a specific action are not met:
        * Command: `{{ "action": "hold", "reason": "No specific command, conditions not met, or already at target." }}`
    * **Unresolvable Error:** If the human command cannot be safely executed due to unresolvable conditions, or if the LLM cannot parse the request:
        * Command: `{{ "action": "error", "message": "Cannot fulfill command: [Explain reason, e.g., 'Invalid coordinates', 'Drone not ready for flight', 'Command unclear']." }}`

---
**Output Format Rules:**

* **You MUST output ONLY a single JSON object.**
* **DO NOT include any conversational text, explanations, markdown fences (```json), or any other characters before or after the JSON.**
* The JSON object must strictly adhere to one of the following schemas:

    * `{{ "action": "takeoff", "altitude_m": <float> }}`
    * `{{ "action": "goto", "latitude_deg": <float>, "longitude_deg": <float>, "altitude_m": <float> }}`
    * `{{ "action": "land" }}`
    * `{{ "action": "rtl" }}`
    * `{{ "action": "arm" }}`
    * `{{ "action": "disarm" }}`
    * `{{ "action": "hold", "reason": "Reason for holding" }}`
    * `{{ "action": "error", "message": "Error description" }}`

**Think Step-by-Step:**
1.  First, analyze the `telemetry_data` and apply **CRITICAL SAFETY FIRST** rules. If any safety rule is triggered, immediately output the corresponding JSON and stop.
2.  If no critical safety rule is triggered, then evaluate the `human_command` in conjunction with `telemetry_data` to determine the most logical action, following the **Human Command Fulfillment & State Management** rules. Consider the drone's current state (armed, in_air, on_ground) before suggesting an action.
3.  If no specific human command action can be performed or understood, resort to the **Default/Fallback Actions**.

   """,

   "prompt3" : f"""
You are an AI drone controller. Based on the drone's current telemetry and the human command, output a single MAVSDK-compatible JSON action.

**Current Telemetry:**
{json.dumps(telemetry_data, indent=2)}

**Human Command:** "{human_command}"

**Response MUST be ONLY a single JSON object, with one of these exact formats:**
* `{{"action": "takeoff", "altitude_m": <float>}}`
* `{{"action": "goto", "latitude_deg": <float>, "longitude_deg": <float>, "altitude_m": <float>}}`
* `{{"action": "land"}}`
* `{{"action": "rtl"}}`
* `{{"action": "arm"}}`
* `{{"action": "disarm"}}`
* `{{"action": "hold", "reason": "Reason for holding"}}`
* `{{"action": "error", "message": "Error description"}}`

**Considerations:**
- Prioritize safe actions if current state demands (e.g., low battery, GPS loss).
- If a command requires multiple steps (e.g., "take off" when disarmed), suggest the immediate next step (e.g., "arm").
- If command is unclear or unexecutable, use "hold" or "error".
""" ,


    }

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt_content['prompt3'],
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
            "human_response": None,
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
                "in_air": True,
                "armed": True
            }
        }
    ]
    
    for t in testcases:
        print(f"Testing Ollama {t['test_type']}:")
        llm_output = await get_ollama_action(t['human_response'], t['telemetry'])
        print(json.dumps(llm_output, indent=2))
    
    
    

if __name__ == "__main__":
    asyncio.run(main_ollama_test())