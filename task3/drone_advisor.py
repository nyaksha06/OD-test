import asyncio
import json
import time

from telemetry import connect_drone, get_drone_telemetry
from ollama_res import get_ollama_action
from drone_action import DroneActionExecutor

Mission_pending = True


async def drone_advisor(Mission):
    print("-- Starting Drone Advisor --")

    drone = None
    try:
        drone = await connect_drone()
    except Exception as e:
        print(f"Failed to connect to drone: {e}")
        return

    action_executor = DroneActionExecutor(drone)
    print("-- Starting Mission --")
    start_time = time.time()

    try:
        while Mission_pending:
            print(f"\n--- Telemetry Update (Time: {time.time() - start_time:.2f}s) ---")

            # Step 1: Get telemetry from MAVSDK (SITL)
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

            # Step 2: Send data to LLMs
            llm_action_request = await get_ollama_action(Mission, telemetry_data)

            # Step 3: Display LLM's suggestion
            print(f"\nOllama's Suggested Action:")
            print(json.dumps(llm_action_request, indent=2))

            # Step 4: Act based on suggestion
            action_type = llm_action_request.get("action")
            llm_action = llm_action_request.get("data", {})
            message = llm_action_request.get("message", "")

            if action_type == "takeoff":
                altitude = llm_action.get("altitude_m")
                if telemetry_data.get("in_air") is False:
                    await action_executor.takeoff_drone(altitude)
                else:
                    print("Skipping takeoff: Already in air.")

            elif action_type == "arm":
                if telemetry_data.get("armed") is False:
                    await action_executor.arm_drone()
                else:
                    print(f"Skipping arm: Already armed or in air.")

            elif action_type == "disarm":
                if telemetry_data.get("armed") is True and telemetry_data.get("in_air") is False:
                    await action_executor.disarm_drone()
                else:
                    print("Skipping disarm: Already disarmed or in air.")

            elif action_type == "goto":
                lat = llm_action.get("latitude_deg")
                lon = llm_action.get("longitude_deg")
                alt = llm_action.get("altitude_m")
                await action_executor.goto_location(lat, lon, alt)

            elif action_type == "land":
                if telemetry_data.get("in_air") is True:
                    await action_executor.land_drone()
                else:
                    print("Skipping land: Not in air.")

            elif action_type == "rtl":
                if telemetry_data.get("in_air") is True:
                    await action_executor.rtl_drone()
                else:
                    print("Skipping RTL: Not in air.")

            elif action_type == "hold":
                await action_executor.hold_drone(llm_action.get("reason", "No specific reason."))

            elif action_type == "error":
                print(f"!!! LLM Error/Intervention Requested: {message} !!!")
                await action_executor.hold_drone("LLM requested human intervention due to error.")

            else:
                print(f"Unknown action type received from LLM: {action_type}. Defaulting to hold.")
                await action_executor.hold_drone("Unknown LLM action.")

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")

    except Exception as e:
        print(f"An unhandled error occurred: {e}")

    finally:
        if drone:
            print("Ensuring drone is disarmed and killed for cleanup...")
            try:
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
                        await drone.action.return_to_launch()
                        async for in_air_status in drone.telemetry.in_air():
                            if not in_air_status:
                                print("Drone landed after RTL attempt.")
                                break
                            await asyncio.sleep(1)
                    except Exception as e:
                        print(f"RTL failed during cleanup: {e}, attempting land.")
                        try:
                            await drone.action.land()
                            async for in_air_status in drone.telemetry.in_air():
                                if not in_air_status:
                                    print("Drone landed after land attempt.")
                                    break
                                await asyncio.sleep(1)
                        except Exception as e_land:
                            print(f"Land failed during cleanup: {e_land}. Force killing.")

                await drone.action.disarm()
                await drone.action.kill()
                print("Drone disarmed and killed successfully.")

            except Exception as e:
                print(f"Error during final drone cleanup (disarm/kill): {e}")
