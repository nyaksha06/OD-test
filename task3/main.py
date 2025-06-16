import asyncio
import json
import time


from telemetry import connect_drone, get_drone_telemetry
from ollama_res import get_ollama_action
from drone_action import DroneActionExecutor


last_human_command = "Start mission"

Mission = " go to lat: 25, lon: 49, altitude : 30 and land there."


# --- Main Logic ---
async def run_ollama_drone_advisor(update_interval_seconds=3):
    print("--- Starting Ollama Drone Advisor ---")

    drone = None
    # Initialize telemetry_data with a default structure to avoid NameError in finally block
    # telemetry_data = {
    #     "armed": False,
    #     "in_air": False,
    #     "health": {
    #         "global_position_ok": False,
    #         "home_position_ok": False,
    #     }
    # }

    try:
        drone = await connect_drone()
    except Exception as e:
        print(f"Failed to connect to drone: {e}")
        print("Ensure PX4 SITL is running and accessible.")
        return

    action_executor = DroneActionExecutor(drone)
    print("Drone connected. Ready for commands.")
    start_time = time.time()
    try:
        while True:
            print(f"\n--- Telemetry Update (Time: {time.time()-start_time}s) ---")
            
            #  Step-1 telemetry from mavsdk(sitl)
            telemetry_data = await get_drone_telemetry(drone) 
            print("Raw Telemetry Snippet:")
            print(f"  Battery: {telemetry_data.get('battery', {}).get('remaining_percent', 'N/A')}%")
            print(f"  GPS Fix: {telemetry_data.get('gps_info', {}).get('fix_type', 'N/A')}D")
            print(f"  In Air: {telemetry_data.get('in_air', 'N/A')}")
            print(f"  Armed: {telemetry_data.get('armed', 'N/A')}")
            print(f"  Flight Mode: {telemetry_data.get('flight_mode', 'N/A')}")
            print(f"  Current Action Executor State: {action_executor.current_action}")
            position = telemetry_data.get("position", {})
            print(f"  Latitude: {position.get('latitude_deg', 'N/A')}")
            print(f"  Longitude: {position.get('longitude_deg', 'N/A')}")
            print(f"  Altitude: {position.get('relative_altitude_m', 'N/A')} m")

            # Step-2. Send data to llms
            llm_action_request = await get_ollama_action(Mission, telemetry_data)
            
            # Step-3. Display llms suggestion
            print(f"\nOllama's Suggested Action :")
            print(json.dumps(llm_action_request, indent=2))

            # step-4. Execute suggested action
            action_type = "takeoff"  #llm_action_request.get("action")
            message = llm_action_request.get("message", "No specific message.")
            
            # --- Action Execution Logic ---
            if action_type == "takeoff":
                altitude =   10  #   llm_action_request.get("altitude_m")
                if telemetry_data.get("in_air") == False:
                    print("-- Drone is taking off...")
                    await action_executor.takeoff_drone(altitude) 
                elif telemetry_data.get("in_air") == False and altitude is not None:
                    await action_executor.takeoff_drone(altitude)
                else:
                    print(f"Skipping takeoff: Already in air or invalid altitude ({altitude}).")
            
            elif action_type == "arm":
                if telemetry_data.get("armed") == False:
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

            elif action_type == "RTL":
                if telemetry_data.get("armed") == True and telemetry_data.get("in_air") == True and telemetry_data.get("health", {}).get("home_position_ok", False):
                    await action_executor.rtl_drone()
                else:
                    print(f"Skipping RTL: Not armed, not in air, or no home position.")

            elif action_type == "hold":
                await action_executor.hold_drone(llm_action_request.get("reason", "No specific reason."))
            
            elif action_type == "error":
                print(f"!!! LLM Error/Intervention Requested: {message} !!!")
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
            try:
                # Get current status before trying to disarm/kill.
                # Use .read() for immediate snapshot of telemetry streams.
                current_armed_status = False
                try:
                    current_armed_status = await drone.telemetry.armed().read()
                except Exception as e_read_armed:
                    print(f"Warning: Could not read armed status during cleanup: {e_read_armed}")

                current_in_air_status = False
                try:
                    current_in_air_status = await drone.telemetry.in_air().read()
                except Exception as e_read_in_air:
                    print(f"Warning: Could not read in_air status during cleanup: {e_read_in_air}")

                if current_armed_status and current_in_air_status:
                    print("Drone still in air and armed, attempting RTL/Land before killing.")
                    try:
                        await drone.action.return_to_launch() # Try RTL first
                        # Wait for it to land
                        async for in_air_status in drone.telemetry.in_air():
                            if not in_air_status:
                                print("Drone landed after RTL attempt.")
                                break
                            await asyncio.sleep(1)
                    except Exception as e:
                        print(f"RTL failed during cleanup: {e}, attempting land.")
                        try:
                            await drone.action.land()
                            # Wait for it to land
                            async for in_air_status in drone.telemetry.in_air():
                                if not in_air_status:
                                    print("Drone landed after land attempt.")
                                    break
                                await asyncio.sleep(1)
                        except Exception as e_land:
                            print(f"Land failed during cleanup: {e_land}. Force killing.")
                
                # Final disarm and kill attempts (safer now that drone should be on ground)
                await drone.action.disarm()
                await drone.action.kill()
                print("Drone disarmed and killed successfully.")
            except Exception as e:
                print(f"Error during final drone cleanup (disarm/kill): {e}")


if __name__ == "__main__":
    try:
        asyncio.run(run_ollama_drone_advisor())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")