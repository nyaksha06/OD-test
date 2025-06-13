
import asyncio
import json
import time

from telemetry import connect_drone, get_drone_telemetry
from ollama_res import get_ollama_response

async def run_ollama_drone_advisor(duration_seconds=300, update_interval_seconds=3):
    """
    Runs the full drone advisor loop using MAVSDK and Ollama.
    """
    print(f"Starting Ollama Drone Advisor for {duration_seconds} seconds...")

    drone = None
    try:
        drone = await connect_drone()
    except Exception as e:
        print(f"Failed to connect to drone: {e}")
        print("Ensure PX4 SITL is running and accessible.")
        return

    print("Drone connected. Starting telemetry and LLM loop.")
    start_time = time.time()

    while (time.time() - start_time) < duration_seconds:
        print(f"\n--- Telemetry Update (Time: {int(time.time() - start_time)}s) ---")
        
        # 1. Get Telemetry from MAVSDK (SITL)
        telemetry_data = await get_drone_telemetry(drone)
        print("Raw Telemetry Snippet:")
        print(f"  Battery: {telemetry_data.get('battery', {}).get('remaining_percent', 'N/A')}%")
        print(f"  GPS Fix: {telemetry_data.get('gps_info', {}).get('fix_type', 'N/A')}D")
        print(f"  In Air: {telemetry_data.get('in_air', 'N/A')}")
        print(f"  Armed: {telemetry_data.get('armed', 'N/A')}")
        print(f"  Flight Mode: {telemetry_data.get('flight_mode', 'N/A')}")

        # 2. Send to Ollama for Reasoning
        ollama_analysis = await get_ollama_response(telemetry_data)
        
        # 3. Display Ollama's Output
        print("\nOllama's Drone Advisory:")
        print(f"  Summary: {ollama_analysis.get('summary', 'No summary.')}")
        if ollama_analysis.get('issues_detected'):
            print(f"  Issues: {', '.join(ollama_analysis['issues_detected'])}")
        print(f"  Suggested Action: {ollama_analysis.get('suggested_action', 'No action suggested.')}")
        
         # Next Step -> commanding the drone from here

        await asyncio.sleep(update_interval_seconds)

    print("\nSimulation Finished.")
    if drone:
        await drone.action.land()
        await asyncio.sleep(10)
        print("Disarming and killing drone...")
        await drone.action.disarm()
        await drone.action.kill()
        print("Drone disarmed and killed.")


if __name__ == "__main__":
    try:
        asyncio.run(run_ollama_drone_advisor())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")