import asyncio
import json
import time


from telemetry import connect_drone, get_drone_telemetry
from ollama_res import get_ollama_action
from drone_action import DroneActionExecutor


