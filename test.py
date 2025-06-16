import asyncio
import json
import time
from mavsdk import System


MAVSDK_CONNECTION_ADDRESS = "udp://:14540" 






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



async def arm_drone(drone):
    print("-- Arming...")
    try:
        await drone.action.arm()
        print("-- Drone armed")
        
        return True
    except Exception as e:
        print(f"Error arming drone: {e}")
        return False



async def takeoff_drone( drone , altitude_m: float):
    print(f"-- Taking off to {altitude_m} meters...")
    try:
        await drone.action.set_takeoff_altitude(altitude_m)
        await drone.action.takeoff()
        print("-- Takeoff command sent")
        # Wait until it reaches target altitude or very close
        async for position in drone.telemetry.position():
            print(position.absolute_altitude_m)
            if position.absolute_altitude_m >= altitude_m * 0.95: # Within 95% of target
                print(f"-- Reached takeoff altitude {position.relative_altitude_m:.2f}m")
                break
            await asyncio.sleep(0.5)
        return True
    except Exception as e:
        print(f"Error taking off: {e}")
        return False
    





async def run():
    print("Starting....")
    drone = None 

    drone = await connect_drone()
    print("arming....")
    await arm_drone(drone)
    print("taking off....")

    await takeoff_drone(drone , 10)

    









if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")    