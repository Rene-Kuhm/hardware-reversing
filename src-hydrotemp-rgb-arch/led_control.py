#!/usr/bin/env python3
"""
Control script for LEDBLE RGB LED on CachyOS
Usage:
  python3 led_control.py on red
  python3 led_control.py off
  python3 led_control.py on 255 128 0  # orange
  python3 led_control.py status        # Returns current RGB state
"""

import asyncio
import sys
import os
from bleak import BleakClient

ADDRESS = os.environ.get("LEDBLE_MAC", "FF:FF:38:61:AB:31")
# The characteristic that controls the LED (read/notify)
CONTROL_CHAR = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Cache file to store last known state
STATE_FILE = os.path.expanduser("~/.local/share/ledble_state")

# Ensure cache directory exists
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)

def read_cached_state():
    """Read the last known state from cache"""
    try:
        with open(STATE_FILE, 'r') as f:
            return f.read().strip()
    except:
        return "off"

def write_cached_state(state):
    """Write state to cache"""
    try:
        with open(STATE_FILE, 'w') as f:
            f.write(state)
    except:
        pass

async def get_led_status():
    """Get current LED status"""
    try:
        async with BleakClient(ADDRESS, timeout=5.0) as client:
            current = await client.read_gatt_char(CONTROL_CHAR)
            power = current[0]
            r = current[1]
            g = current[2]
            b = current[3]
            
            if power == 0:
                return {"state": "off", "r": 0, "g": 0, "b": 0}
            else:
                return {"state": "on", "r": r, "g": g, "b": b}
    except Exception as e:
        # If we can't connect, return cached state
        cached = read_cached_state()
        if cached == "off":
            return {"state": "off", "r": 0, "g": 0, "b": 0}
        else:
            parts = cached.split(',')
            return {"state": "on", "r": int(parts[0]), "g": int(parts[1]), "b": int(parts[2])}

async def set_led(state, r=0, g=0, b=0):
    """Set LED state and color"""
    async with BleakClient(ADDRESS, timeout=10.0) as client:
        # Read current state to preserve fixed bytes
        current = await client.read_gatt_char(CONTROL_CHAR)
        current = bytearray(current)
        
        # Modify only the relevant bytes
        current[0] = 0x01 if state == "on" else 0x00  # Power
        if state == "on":
            current[1] = r & 0xFF  # Red
            current[2] = g & 0xFF  # Green
            current[3] = b & 0xFF  # Blue
        
        # Write the new state
        await client.write_gatt_char(CONTROL_CHAR, current, response=False)
        
        # Update cache
        if state == "on":
            write_cached_state(f"{r},{g},{b}")
        else:
            write_cached_state("off")
        
        return {"state": state, "r": r, "g": g, "b": b}

def get_color_name(r, g, b):
    """Get a friendly name for the color"""
    color_map = {
        (255, 0, 0): "red",
        (0, 255, 0): "green",
        (0, 0, 255): "blue",
        (255, 255, 255): "white",
        (255, 255, 0): "yellow",
        (255, 0, 255): "purple",
        (0, 255, 255): "cyan",
        (255, 128, 0): "orange",
        (255, 192, 203): "pink",
        (0, 0, 0): "black"
    }
    
    # Exact match
    if (r, g, b) in color_map:
        return color_map[(r, g, b)]
    
    # Find closest
    min_dist = float('inf')
    closest = "custom"
    for (cr, cg, cb), name in color_map.items():
        dist = (r-cr)**2 + (g-cg)**2 + (b-cb)**2
        if dist < min_dist:
            min_dist = dist
            closest = name
    
    if min_dist < 10000:  # Threshold for "close enough"
        return closest
    return f"{r},{g},{b}"

def print_usage():
    print("Usage:")
    print("  python3 led_control.py on red")
    print("  python3 led_control.py on green")
    print("  python3 led_control.py on blue")
    print("  python3 led_control.py on white")
    print("  python3 led_control.py on <r> <g> <b>  # 0-255")
    print("  python3 led_control.py off")
    print("  python3 led_control.py status")
    print("  python3 led_control.py toggle")
    print("")
    print("Examples:")
    print("  python3 led_control.py on 255 0 0    # Red")
    print("  python3 led_control.py on 0 255 0    # Green")
    print("  python3 led_control.py on 0 0 255    # Blue")
    print("  python3 led_control.py on 255 255 0  # Yellow")
    print("  python3 led_control.py on 255 0 255  # Purple")
    print("  python3 led_control.py on 0 255 255  # Cyan")
    print("  python3 led_control.py toggle        # Toggle on/off")

async def main():
    if len(sys.argv) < 2:
        print_usage()
        return
    
    command = sys.argv[1].lower()
    
    if command == "off":
        result = await set_led("off")
        print(f"LED OFF")
    
    elif command == "on":
        if len(sys.argv) == 2:
            # Default to white if no color specified
            result = await set_led("on", 255, 255, 255)
            print(f"LED ON - White")
        elif len(sys.argv) == 3:
            color = sys.argv[2].lower()
            colors = {
                "red": (255, 0, 0),
                "green": (0, 255, 0),
                "blue": (0, 0, 255),
                "white": (255, 255, 255),
                "yellow": (255, 255, 0),
                "purple": (255, 0, 255),
                "cyan": (0, 255, 255),
                "orange": (255, 128, 0),
                "pink": (255, 192, 203)
            }
            if color in colors:
                r, g, b = colors[color]
                result = await set_led("on", r, g, b)
                print(f"LED ON - {color}")
            else:
                print(f"Unknown color: {color}")
                print_usage()
        elif len(sys.argv) == 5:
            try:
                r = int(sys.argv[2])
                g = int(sys.argv[3])
                b = int(sys.argv[4])
                if all(0 <= x <= 255 for x in [r, g, b]):
                    result = await set_led("on", r, g, b)
                    color_name = get_color_name(r, g, b)
                    print(f"LED ON - {color_name}")
                else:
                    print("Error: RGB values must be between 0 and 255")
            except ValueError:
                print("Error: RGB values must be integers")
        else:
            print_usage()
    
    elif command == "status":
        status = await get_led_status()
        if status["state"] == "off":
            print("off")
        else:
            color_name = get_color_name(status["r"], status["g"], status["b"])
            print(f"on {color_name}")
    
    elif command == "toggle":
        status = await get_led_status()
        if status["state"] == "on":
            await set_led("off")
            print("LED OFF")
        else:
            await set_led("on", 255, 255, 255)
            print("LED ON - White")
    
    else:
        print(f"Unknown command: {command}")
        print_usage()

if __name__ == "__main__":
    asyncio.run(main())
