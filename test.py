import cv2
import requests
import time
from dronekit import connect, VehicleMode, LocationGlobalRelative

# ---------------- Drone Setup ---------------- #
print("[INFO] Connecting to SITL...")
vehicle = connect('tcp:127.0.0.1:5760', wait_ready=True)
vehicle.mode = VehicleMode("GUIDED")
vehicle.armed = True
while not vehicle.armed:
    print("[INFO] Waiting for arming...")
    time.sleep(1)

vehicle.simple_takeoff(10)
print("[INFO] Taking off...")

# ---------------- Ollama Query ---------------- #
def ask_ollama(objects):
    prompt = f"I detected: {', '.join(objects)}. What should the drone do? Keep it short and clear."
    try:
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3",
            "prompt": prompt
        })
        return res.json().get("response", "").strip()
    except Exception as e:
        print(f"[ERROR] Ollama call failed: {e}")
        return ""

# ---------------- Drone Action ---------------- #
def execute_command(response):
    cmd = response.lower()
    loc = vehicle.location.global_relative_frame

    if "land" in cmd:
        print("[ACTION] Landing...")
        vehicle.mode = VehicleMode("LAND")
    elif "forward" in cmd:
        print("[ACTION] Moving forward...")
        target = LocationGlobalRelative(loc.lat + 0.00005, loc.lon, loc.alt)
        vehicle.simple_goto(target)
    elif "hold" in cmd or "hover" in cmd:
        print("[ACTION] Holding position.")
        # Do nothing
    else:
        print("[ACTION] Unknown or no actionable command.")

# ---------------- Object Detection (Mock) ---------------- #
def mock_detect_objects(frame):
    # Replace this with real detection
    return ["person"] if frame.sum() % 2 == 0 else ["tree"]

# ---------------- Main Video Loop ---------------- #
cap = cv2.VideoCapture("test_video.mp4")  # Replace with your video path
frame_count = 0

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    if frame_count % 30 != 0:
        continue  # Process every 30th frame

    detected = mock_detect_objects(frame)
    print(f"[DETECT] Objects: {detected}")

    if detected:
        ollama_resp = ask_ollama(detected)
        print(f"[OLLAMA] Response: {ollama_resp}")
        execute_command(ollama_resp)

    time.sleep(2)

cap.release()
vehicle.close()
