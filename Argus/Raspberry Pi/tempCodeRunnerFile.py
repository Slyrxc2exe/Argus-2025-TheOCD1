"""
PROJECT ARGUS - Raspberry Pi "Brain" & Web Server (v2 - Simplified)
-------------------------------------------------------------------
This Python script runs on the Raspberry Pi.
- WEB SERVER: Runs a Flask dashboard showing Distance and Battery.
- ROVER BRAIN: Communicates with the Arduino over SPI.

*** NOW INCLUDES A "TESTING MODE" TO RUN ON WINDOWS/MAC ***
"""

import time
import threading
import struct
from flask import Flask, jsonify, render_template, url_for

# --- HARDWARE/TESTING DETECTION ---
try:
    # Try to import the real Pi-only library
    import spidev
    ON_PI = True
except ImportError:
    # If it fails, we're not on a Pi.
    ON_PI = False

# --- SPI COMMUNICATION SETUP ---

# SPI Command definitions (MUST match the Arduino .ino file)
CMD_STOP = 0x00
CMD_FORWARD = 0x01
CMD_REVERSE = 0x02
CMD_TURN_LEFT = 0x03
CMD_TURN_RIGHT = 0x04
CMD_GET_SENSOR_DATA = 0x10

# Data Structure format (MUST match the Arduino 'struct SensorData')
SENSOR_DATA_FORMAT = '<hb'
SENSOR_DATA_NUM_BYTES = 3

# Initialize SPI (Real or "Mock")
if ON_PI:
    spi = spidev.SpiDev()
    spi.open(0, 0)  # Open SPI bus 0, device (CS) 0
    spi.max_speed_hz = 1000000  # Set SPI speed to 1MHz
else:
    # --- This is our "Mock" SPI object for testing ---
    print("="*40)
    print(" WARNING: 'spidev' library not found.")
    print(" RUNNING IN TESTING/MOCK MODE.")
    print(" Hardware commands will be simulated.")
    print("="*40)
    class MockSpiDev:
        def xfer(self, bytes_to_send):
            # When asked for data, return a fake response
            if bytes_to_send[0] == CMD_GET_SENSOR_DATA:
                # [Ack_Byte, Dist_High, Dist_Low, Battery_Byte]
                return [0xFF, 0x32, 0x00, 0x5A] # 50cm, 90% battery
            return [0xFF] # Default "OK" response
    spi = MockSpiDev()
    # --- End of Mock SPI ---

# --- FLASK WEB APP SETUP ---
app = Flask(__name__)

# --- GLOBAL ROVER DATA ---
rover_data = {
    "state": "INITIALIZING",
    "distance": 0,
    "battery_life": 0
}
data_lock = threading.Lock()

# --- SPI HELPER FUNCTIONS ---

def send_motor_command(command):
    """Sends a 1-byte motor command to the Arduino."""
    if not ON_PI:
        # Don't try to send real commands in test mode
        # print(f"[MOCK] Sending command: {command}")
        return 
    
    try:
        resp = spi.xfer([command])
    except Exception as e:
        print(f"SPI Error (Command): {e}")

def get_sensor_data():
    """
    Requests the 3-byte sensor packet from the Arduino.
    Parses the data and returns the values.
    """
    try:
        bytes_to_send = [CMD_GET_SENSOR_DATA, 0, 0, 0]
        resp = spi.xfer(bytes_to_send)
        data_packet = resp[1:]
        d, b = struct.unpack(SENSOR_DATA_FORMAT, bytearray(data_packet))
        return d, b
        
    except Exception as e:
        if ON_PI: # Only print errors if we are on the Pi
            print(f"SPI Error (Data): {e}")
        # Return safe default values in case of an error
        return 0, 0

# --- ROVER "BRAIN" LOGIC ---

def rover_main_loop():
    """
    This is the main "brain" of your rover.
    """
    global rover_data
    print("Rover main loop started.")
    
    time.sleep(2) # Give sensors a moment to stabilize
    
    # Counter for simulating data changes in test mode
    test_counter = 0

    while True:
        dist, battery = 0, 0

        if ON_PI:
            # --- Get REAL data from Arduino ---
            dist, battery = get_sensor_data()
        else:
            # --- Generate FAKE data for testing ---
            test_counter += 1
            if test_counter > 50:
                test_counter = 0
            
            if test_counter < 25:
                dist = 50 # 50cm
            else:
                dist = 15 # 15cm (obstacle)
            
            battery = 90 - (test_counter // 5) # Battery slowly drains
            # --- End of Fake Data ---

        # 2. === NAVIGATION & HAZARD LOGIC (STATE MACHINE) ===
        OBSTACLE_DISTANCE = 20  # In cm
        LOW_BATTERY = 10        # In percent
        
        new_state = rover_data["state"] # Get current state
        
        if battery <= LOW_BATTERY:
            new_state = "LOW_BATTERY"
            send_motor_command(CMD_STOP)
            
        elif dist <= OBSTACLE_DISTANCE and dist > 0: # (dist > 0 filters bad readings)
            new_state = "AVOIDING_OBSTACLE"
            if ON_PI: # Only send real commands on the Pi
                send_motor_command(CMD_REVERSE) 
                time.sleep(0.5)
                send_motor_command(CMD_TURN_LEFT)
                time.sleep(0.7)
                send_motor_command(CMD_STOP)
            
        else:
            new_state = "SCOUTING"
            send_motor_command(CMD_FORWARD)

        # 3. === SAFELY UPDATE THE GLOBAL DATA ===
        with data_lock:
            rover_data["state"] = new_state
            rover_data["distance"] = dist
            rover_data["battery_life"] = battery
            
        # Print to console for debugging
        print(f"State: {new_state} | Dist: {dist} | Battery: {battery}%")
            
        # Loop delay
        time.sleep(0.2) # Run the main logic loop 5 times per second

# --- WEB SERVER ROUTES ---

@app.route('/')
def index():
    """ Serves the main Dashboard page. """
    # This now renders the new, smaller index.html
    return render_template('index.html')

@app.route('/mission')
def mission():
    """ Serves the Mission Briefing page. """
    # This is the new route for your "about" page
    return render_template('mission.html')

@app.route('/data')
def get_data_route():
    """ This is the route the JavaScript will fetch from. """
    with data_lock:
        data_copy = rover_data.copy()
    return jsonify(data_copy)

# --- NEW ROUTE FOR MISSION CONTROL BUTTONS ---
@app.route('/command', methods=['POST'])
def handle_command():
    """ Handles POST requests from the mission control buttons. """
    try:
        data = request.get_json()
        command = data.get('command')
        
        if not command:
            return jsonify({"status": "error", "message": "No command provided"}), 400
            
        print(f"[COMMAND RECEIVED] {command}")
        
        # ---
        # TODO: Add logic here to send SPI commands to the Arduino
        # based on the 'command' string.
        # ---
        # Example:
        # if command == "START":
        #     send_motor_command(CMD_FORWARD) # Or a new "CMD_START_MISSION"
        # elif command == "PAUSE":
        #     send_motor_command(CMD_STOP)
        
        return jsonify({"status": "success", "message": f"Command '{command}' received"})
        
    except Exception as e:
        print(f"[COMMAND ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- MAIN ENTRY POINT ---

if __name__ == '__main__':
    try:
        # 1. Start the Rover's "Brain" in its own thread
        rover_thread = threading.Thread(target=rover_main_loop, daemon=True)
        rover_thread.start()
        
        # 2. Start the Web Server
        if not ON_PI:
             print(" Access dashboard at: http://127.0.0.1:5000")
        else:
            print("\n" + "="*40)
            print(" PROJECT ARGUS SERVER (v2) IS LIVE")
            print(" Access dashboard at: http://<YOUR_PI_IP_ADDRESS>:5000")
            print("="*40 + "\n")
        
        app.run(host='0.0.0.0', port=5000)

    except KeyboardInterrupt:
        print("\nShutting down...")
        if ON_PI:
            send_motor_command(CMD_STOP)
            spi.close()
    finally:
        if ON_PI:
            send_motor_command(CMD_STOP)
            spi.close()


