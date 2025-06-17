# drone_action_executor.py
import asyncio
from mavsdk import System
from mavsdk.telemetry import FlightMode

class DroneActionExecutor:
    def __init__(self, drone: System):
        self.drone = drone
        self.current_action = "none" 
        self.target_latitude = None
        self.target_longitude = None
        self.target_altitude = None

    async def arm_drone(self):
        print("-- Arming...")
        try:
            await self.drone.action.arm()
            print("-- Drone armed")
            self.current_action = "armed"
            return True
        except Exception as e:
            print(f"Error arming drone: {e}")
            return False

    async def disarm_drone(self):
        print("-- Disarming...")
        try:
            await self.drone.action.disarm()
            print("-- Drone disarmed")
            self.current_action = "disarmed"
            return True
        except Exception as e:
            print(f"Error disarming drone: {e}")
            return False

    async def takeoff_drone(self, altitude_m: float):

        
        print(f"-- Taking off to {altitude_m} meters...")
        try:
            await self.drone.action.set_takeoff_altitude(altitude_m)
            await self.drone.action.takeoff()
            self.current_action = "taking_off"
            print("-- Takeoff command sent")
            async for position in self.drone.telemetry.position():
                if position.relative_altitude_m >= altitude_m * 0.95: # Within 95% of target
                    print(f"-- Reached takeoff altitude {position.relative_altitude_m:.2f}m")
                    break
                await asyncio.sleep(0.5)
            self.current_action = "in_air"
            return True
        except Exception as e:
            print(f"Error taking off: {e}")
            return False

    async def goto_location(self, latitude: float, longitude: float, altitude: float):
        print(f"-- Going to Lat: {latitude:.4f}, Lon: {longitude:.4f}, Alt: {altitude:.2f}m")
        self.target_latitude = latitude
        self.target_longitude = longitude
        self.target_altitude = altitude
        
        try:
            await self.drone.action.goto_location(latitude, longitude, altitude, 0.0) # Last param is yaw_deg (0 for no specific yaw)
            self.current_action = "going_to_location"
            print("-- Goto command sent")

            # Monitor progress towards target
            async for position in self.drone.telemetry.position():
                dist_to_target = self._calculate_distance(
                    position.latitude_deg, position.longitude_deg,
                    self.target_latitude, self.target_longitude
                )
                alt_diff = abs(position.relative_altitude_m - self.target_altitude)

                if dist_to_target < 2.0 and alt_diff < 1.0: # Within 2m horizontal, 1m vertical
                    print(f"-- Reached target location. Distance: {dist_to_target:.2f}m, Altitude difference: {alt_diff:.2f}m")
                    break
                
                # Also check flight mode for manual override or RTL
                async for flight_mode in self.drone.telemetry.flight_mode():
                    if flight_mode != FlightMode.POSCTL and flight_mode != FlightMode.AUTO: # Or whatever mode 'goto' uses
                        print(f"-- Flight mode changed to {flight_mode.name}, stopping goto monitoring.")
                        self.current_action = "monitoring"
                        return False # Action interrupted
                    break # Get current flight mode and break

                await asyncio.sleep(1) # Check every second
            self.current_action = "at_target"
            return True
        except Exception as e:
            print(f"Error going to location: {e}")
            return False

    async def land_drone(self):
        print("-- Landing...")
        try:
            await self.drone.action.land()
            self.current_action = "landing"
            print("-- Land command sent")
            async for in_air in self.drone.telemetry.in_air():
                if not in_air:
                    print("-- Drone landed.")
                    break
                await asyncio.sleep(0.5)
            self.current_action = "on_ground"
            return True
        except Exception as e:
            print(f"Error landing: {e}")
            return False

    async def rtl_drone(self):
        print("-- Initiating Return To Launch...")
        try:
            await self.drone.action.return_to_launch()
            self.current_action = "returning_to_launch"
            print("-- RTL command sent")
            # Monitor until landed
            async for in_air in self.drone.telemetry.in_air():
                if not in_air:
                    print("-- Drone returned and landed.")
                    break
                await asyncio.sleep(0.5)
            self.current_action = "on_ground"
            return True
        except Exception as e:
            print(f"Error initiating RTL: {e}")
            return False

    async def hold_drone(self, reason: str):
        print(f"-- Holding current position. Reason: {reason}")
        try:
            # Set to HOLD flight mode if not already
            async for flight_mode in self.drone.telemetry.flight_mode():
                if flight_mode != FlightMode.HOLD:
                    await self.drone.action.hold()
                    print("-- Set to HOLD mode.")
                break
            self.current_action = "holding"
            return True
        except Exception as e:
            print(f"Error setting to hold: {e}")
            return False

    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        # A simple approximation for distance for small distances (Haversine formula for accuracy)
        # For this simulation, we'll use a very crude estimate, but for real, use geopy or similar.
        # This is just to check if it's "close enough" for the SITL loop.
        R = 6371000 # Earth radius in meters
        d_lat = (lat2 - lat1) * 3.14159 / 180.0
        d_lon = (lon2 - lon1) * 3.14159 / 180.0
        a = (d_lat/2)**2 + (d_lon/2)**2 * 0.9 # crude cosine(lat) factor
        c = 2 * 0.1 # crude asin(sqrt(a))
        return R * c # Very rough approximation