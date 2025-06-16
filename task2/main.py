# main_ollama_drone_advisor.py
import asyncio
import json
import time
import queue
import threading

from telemetry import connect_drone, get_drone_telemetry
from ollama_res import get_ollama_action
from drone_action import DroneActionExecutor

# Global variable to store the last human command
last_human_command = "Start mission" # Initial command for the LLM

async def run_ollama_drone_advisor(update_interval_seconds=3):
    print("--- Starting Ollama Drone Advisor ---")

    drone = None
    try:
        drone = await connect_drone()
    except Exception as e:
        print(f"Failed to connect to drone: {e}")
        print("Ensure PX4 SITL is running and accessible.")
        return

    action_executor = DroneActionExecutor(drone)
    print("Drone connected. Ready for commands.")

    # Task to continuously monitor human input
    # async def human_input_monitor():
    #     global last_human_command
    #     while True:
    #         new_command = await asyncio.to_thread(input, "\nEnter command for drone (e.g., 'Take off to 10m', 'Go to 23.0225, 72.5714 at 50m', 'Land', 'RTL', 'Status'): ")
    #         if new_command.strip():
    #             last_human_command = new_command.strip()
    #             print(f"Human command received: '{last_human_command}'")
    #         await asyncio.sleep(0.1) # Prevent busy-waiting
    input_queue = queue.Queue()

    def _get_input_in_thread(prompt, input_q):
        try:
            input_q.put(input(prompt))
        except Exception as e:
            print(f"[Error in input thread]: {e}")

    async def human_input_monitor():
        print("is this part running???")
        global last_human_command
        # Start the input thread if it's not running or completed
        input_thread = None
        while True:
            if input_thread is None or not input_thread.is_alive():
                # Start new input thread
                input_thread = threading.Thread(
                    target=_get_input_in_thread,
                    args=("\nEnter command for drone (e.g., 'Take off to 10m', 'Go to 23.0225, 72.5714 at 50m', 'Land', 'RTL', 'Status'): ", input_queue)
                )
                input_thread.daemon = True # Allow main program to exit even if thread is running
                input_thread.start()

            # Check if input is available without blocking
            try:
                new_command = input_queue.get_nowait()
                if new_command.strip():
                    last_human_command = new_command.strip()
                    print(f"Human command received: '{last_human_command}'")
            except queue.Empty:
                pass # No new input yet

            await asyncio.sleep(0.1) # Check frequently
    # Start the human input monitor as a background task
    input_task = asyncio.create_task(human_input_monitor())

    try:
        while True:
            print(f"\n--- Telemetry Update (Time: {int(time.time())}s) ---")
            
            # 1. Get Telemetry from MAVSDK (SITL)
            telemetry_data = await get_drone_telemetry(drone)
            print("Raw Telemetry Snippet:")
            print(f"  Battery: {telemetry_data.get('battery', {}).get('remaining_percent', 'N/A')}%")
            print(f"  GPS Fix: {telemetry_data.get('gps_info', {}).get('fix_type', 'N/A')}D")
            print(f"  In Air: {telemetry_data.get('in_air', 'N/A')}")
            print(f"  Armed: {telemetry_data.get('armed', 'N/A')}")
            print(f"  Flight Mode: {telemetry_data.get('flight_mode', 'N/A')}")
            print(f"  Current Action Executor State: {action_executor.current_action}")

            # 2. Send current human command and telemetry to Ollama for Reasoning
            # We are sending the *last* command, allowing LLM to adapt based on current state
            llm_action_request = await get_ollama_action(last_human_command, telemetry_data)
            
            # 3. Display Ollama's Suggested Action
            print("\nOllama's Suggested Action:")
            print(json.dumps(llm_action_request, indent=2))

            # 4. Execute the Suggested Action via DroneActionExecutor
            action_type = llm_action_request.get("action")
            message = llm_action_request.get("message", "No specific message.")
            
            if action_type == "takeoff":
                altitude = llm_action_request.get("altitude_m")
                if telemetry_data.get("armed") == False:
                    print("-- Drone not armed, LLM suggests arming first.")
                    await action_executor.arm_drone()
                    # After arming, the next loop iteration should lead to takeoff
                    await asyncio.sleep(update_interval_seconds) # Give time for arming
                    continue # Skip to next loop iteration
                elif telemetry_data.get("in_air") == False and altitude is not None:
                    await action_executor.takeoff_drone(altitude)
                else:
                    print(f"Skipping takeoff: Already in air or invalid altitude ({altitude}).")
            
            elif action_type == "arm":
                if telemetry_data.get("armed") == False and telemetry_data.get("in_air") == False:
                    await action_executor.arm_drone()
                else:
                    print(f"Skipping arm: Already armed ({telemetry_data.get('armed')}) or in air ({telemetry_data.get('in_air')}).")

            elif action_type == "disarm":
                if telemetry_data.get("armed") == True and telemetry_data.get("in_air") == False:
                    await action_executor.disarm_drone()
                else:
                    print(f"Skipping disarm: Already disarmed or in air ({telemetry_data.get('in_air')}).")

            elif action_type == "goto":
                lat = llm_action_request.get("latitude_deg")
                lon = llm_action_request.get("longitude_deg")
                alt = llm_action_request.get("altitude_m")
                if telemetry_data.get("armed") == True and telemetry_data.get("in_air") == True and telemetry_data.get("health", {}).get("global_position_ok", False) and lat is not None and lon is not None and alt is not None:
                    await action_executor.goto_location(lat, lon, alt)
                else:
                    print(f"Skipping goto: Not armed, not in air, no GPS, or invalid coordinates.")
            
            elif action_type == "land":
                if telemetry_data.get("armed") == True and telemetry_data.get("in_air") == True:
                    await action_executor.land_drone()
                else:
                    print(f"Skipping land: Not armed or not in air.")

            elif action_type == "rtl":
                if telemetry_data.get("armed") == True and telemetry_data.get("in_air") == True and telemetry_data.get("health", {}).get("home_position_ok", False):
                    await action_executor.rtl_drone()
                else:
                    print(f"Skipping RTL: Not armed, not in air, or no home position.")

            elif action_type == "hold":
                await action_executor.hold_drone(llm_action_request.get("reason", "No specific reason."))
            
            elif action_type == "error":
                print(f"!!! LLM Error/Intervention Requested: {message} !!!")
                # In a real system, you'd alert the human operator prominently here
                # and potentially halt automatic execution.
                # For now, we'll continue to monitor.
                await action_executor.hold_drone("LLM requested human intervention due to error.")
            
            else:
                print(f"Unknown action type received from LLM: {action_type}. Defaulting to hold.")
                await action_executor.hold_drone("Unknown LLM action.")

            await asyncio.sleep(update_interval_seconds)

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"An unhandled error occurred: {e}")
    finally:
        if drone:
            print("Ensuring drone is disarmed and killed for cleanup...")
            # Attempt to disarm and kill only if drone is not already disarmed and on ground
            if telemetry_data.get("armed", False) and telemetry_data.get("in_air", False):
                print("Drone still in air and armed, attempting RTL/Land before killing.")
                try:
                    await drone.action.return_to_launch() # Try RTL first
                    async for in_air_status in drone.telemetry.in_air():
                        if not in_air_status: break
                        await asyncio.sleep(1)
                except Exception as e:
                    print(f"RTL failed during cleanup: {e}, attempting land.")
                    try:
                        await drone.action.land()
                        async for in_air_status in drone.telemetry.in_air():
                            if not in_air_status: break
                            await asyncio.sleep(1)
                    except Exception as e_land:
                        print(f"Land failed during cleanup: {e_land}. Force killing.")
            
            # Final disarm and kill attempts
            try:
                await drone.action.disarm()
                await drone.action.kill()
                print("Drone disarmed and killed successfully.")
            except Exception as e:
                print(f"Error during final drone cleanup (disarm/kill): {e}")

        if input_task:
            input_task.cancel()
            try:
                await input_task # Await to ensure cancellation propagates
            except asyncio.CancelledError:
                pass # Expected during graceful shutdown







if __name__ == "__main__":
    try:
        asyncio.run(run_ollama_drone_advisor())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")


