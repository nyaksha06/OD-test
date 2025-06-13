# mavsdk_telemetry_collector.py
import asyncio
from mavsdk import System


MAVSDK_CONNECTION_ADDRESS = "udp://:14540" 

async def get_drone_telemetry(drone: System):
    telemetry_data = {}

    #position
    async for position in drone.telemetry.position():
        telemetry_data["position"] = {
            "latitude_deg": position.latitude_deg,
            "longitude_deg": position.longitude_deg,
            "relative_altitude_m": position.relative_altitude_m
        }
        break # Get current value and break

    #velocity
    async for velocity_ned in drone.telemetry.velocity_ned():
        telemetry_data["velocity_ned"] = {
            "north_m_s": velocity_ned.north_m_s,
            "east_m_s": velocity_ned.east_m_s,
            "down_m_s": velocity_ned.down_m_s
        }
        break

    #attitude
    async for attitude_euler in drone.telemetry.attitude_euler():
        telemetry_data["attitude_euler"] = {
            "roll_deg": attitude_euler.roll_deg,
            "pitch_deg": attitude_euler.pitch_deg,
            "yaw_deg": attitude_euler.yaw_deg
        }
        break

    #battery status
    async for battery in drone.telemetry.battery():
        telemetry_data["battery"] = {
            "remaining_percent": int(battery.remaining_percent * 100),
            "voltage_v": round(battery.voltage_v, 2)
        }
        break

    #flight mode
    async for flight_mode in drone.telemetry.flight_mode():
        telemetry_data["flight_mode"] = flight_mode.name
        break

    #GPS info
    async for gps_info in drone.telemetry.gps_info():
        telemetry_data["gps_info"] = {
            "num_satellites": gps_info.num_satellites,
            "fix_type": gps_info.fix_type.value # 0: No Fix, 1: No GPS, 2: 2D Fix, 3: 3D Fix
        }
        break

    #health status
    async for health in drone.telemetry.health():
        telemetry_data["health"] = {
            # "gyro_calibrated": health.gyro_calibrated,
            # "accel_calibrated": health.accel_calibrated,
            # "mag_calibrated": health.mag_calibrated,
            # "baro_calibrated": health.baro_calibrated,
            # "gps_ok": health.gps_ok,
            # "home_position_ok": health.home_position_ok,
            "armable": health.armable,
            "armed": health.armed,
            "global_position_ok": health.global_position_ok,
            "local_position_ok": health.local_position_ok
        }
        break
    
    async for in_air in drone.telemetry.in_air():
        telemetry_data["in_air"] = in_air
        break
    
    async for armed in drone.telemetry.armed():
        telemetry_data["armed"] = armed
        break

    return telemetry_data

async def connect_drone():
    print(f"Connecting to drone at {MAVSDK_CONNECTION_ADDRESS}...")
    drone = System()
    await drone.connect(system_address=MAVSDK_CONNECTION_ADDRESS)

    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Drone connected!")
            break
        await asyncio.sleep(1) 
    
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            print("Drone has a good global position estimate.")
            break
        await asyncio.sleep(1) 

    return drone


async def main_collector_test():
    drone = await connect_drone()
    print("Collecting initial telemetry...")
    telemetry = await get_drone_telemetry(drone)
    print(json.dumps(telemetry, indent=2))
    await drone.action.land()
    await asyncio.sleep(10)
    await drone.action.disarm() # Clean up
    await drone.action.kill() # Clean up

if __name__ == "__main__":
    import json
    try:
        asyncio.run(main_collector_test())
    except Exception as e:
        print(f"Error during initial telemetry collection: {e}")