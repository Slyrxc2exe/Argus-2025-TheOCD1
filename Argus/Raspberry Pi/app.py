import time
import threading
import struct
import platform

# --- Try to import Pi-specific library ---
try:
    import spidev
    ON_PI = True
except ImportError:
    ON_PI = False
    print("[INFO] spidev library not found. Running in MOCK mode.")

from flask import Flask, jsonify, render_template, request

# --- SPI COMMUNICATION SETUP (for Pi) ---
if ON_PI:
    spi = spidev.SpiDev()
    spi.open(0, 0)  # Open SPI bus 0, device (CS) 0
    spi.max_speed_hz = 1000000 # 1MHz

# SPI Command definitions
CMD_STOP = 0x00
CMD_FORWARD = 0x01
CMD_REVERSE = 0x02
CMD_TURN_LEFT = 0x03
CMD_TURN_RIGHT = 0x04
CMD_GET_SENSOR_DATA = 0x10

# Data Structure format (must match Arduino)
SENSOR_DATA_FORMAT = '<hb' # 2-byte short (distance), 1-byte char (battery)
SENSOR_DATA_NUM_BYTES = 3

# --- FLASK WEB APP SETUP ---
app = Flask(__name__)

# --- Global Rover Data ---
rover_data = {
    "state": "INITIALIZING",
    "distance": 0,
    "battery_life": 0
}
data_lock = threading.Lock()
last_command = "PAUSE" # Store the last command sent

# --- SPI HELPER FUNCTIONS ---

def send_motor_command_to_pi(command):
    """Sends a 1-byte motor command to the Arduino."""
    global last_command
    last_command = command # Store the command
    
    if not ON_PI: return # Don't do anything if not on Pi
    
    try:
        spi.xfer([command])
    except Exception as e:
        print(f"SPI Error (Command): {e}")

def get_sensor_data_from_pi():
    """Requests and parses the sensor data packet from the Arduino."""
    if not ON_PI: return 0, 0 # Return mock data if not on Pi
    
    try:
        bytes_to_send = [CMD_GET_SENSOR_DATA] + [0] * SENSOR_DATA_NUM_BYTES
        resp = spi.xfer(bytes_to_send)
        
        data_packet = resp[1:] # First byte is junk, get the rest
        
        d, b = struct.unpack(SENSOR_DATA_FORMAT, bytearray(data_packet))
        return d, b
        
    except Exception as e:
        print(f"SPI Error (Data): {e}")
        return 0, 0 # Return safe defaults

# --- ROVER "BRAIN" LOGIC ---

def rover_main_loop():
    """
    This is the main "brain" of your rover.
    It runs in a separate thread.
    """
    global rover_data
    print("Rover main loop started.")
    
    while True:
        # 1. === GET REAL SENSOR DATA FROM ARDUINO ===
        dist, battery = get_sensor_data_from_pi()
        
        # 2. === NAVIGATION & HAZARD LOGIC (STATE MACHINE) ===
        OBSTACLE_DISTANCE = 20  # In cm
        LOW_BATTERY = 10        # In percent
        
        new_state = "PAUSED" # Default state
        
        if last_command == "START_MISSION":
            if battery <= LOW_BATTERY:
                new_state = "LOW_BATTERY"
                send_motor_command_to_pi(CMD_STOP)
            elif dist <= OBSTACLE_DISTANCE and dist > 0:
                new_state = "AVOIDING_OBSTACLE"
                send_motor_command_to_pi(CMD_TURN_LEFT) # Or your preferred logic
            else:
                new_state = "SCOUTING"
                send_motor_command_to_pi(CMD_FORWARD)
        
        elif last_command == "PAUSE":
            new_state = "PAUSED"
            send_motor_command_to_pi(CMD_STOP)
        
        elif last_command == "RETURN_HOME":
            new_state = "RETURN_HOME"
            # Add custom logic for returning home
            send_motor_command_to_pi(CMD_FORWARD) # Placeholder
            
        elif last_command == "SHUTDOWN":
            new_state = "SHUTDOWN"
            send_motor_command_to_pi(CMD_STOP)

        # 3. === SAFELY UPDATE THE GLOBAL DATA ===
        with data_lock:
            rover_data["state"] = new_state
            rover_data["distance"] = dist
            rover_data["battery_life"] = battery
        
        # 4. === Print to Pi's console for debugging ===
        if ON_PI:
            print(f"State: {new_state} | Dist: {dist} | Battery: {battery}%")
            
        time.sleep(0.2) # Run the logic loop 5 times per second

# --- WEB SERVER ROUTES ---

@app.route('/')
def index_page():
    """ Serves the main Dashboard page. """
    return render_template('index.html', current_page='dashboard')

@app.route('/data')
def get_data_route():
    """ This is the route the JavaScript will fetch from. """
    with data_lock:
        data_copy = rover_data.copy()
    return jsonify(data_copy)

@app.route('/command', methods=['POST'])
def handle_command():
    """ Handles incoming commands from the dashboard buttons. """
    global last_command
    try:
        data = request.get_json()
        command = data.get('command')
        
        if command in ["START_MISSION", "PAUSE", "RETURN_HOME", "SHUTDOWN"]:
            print(f"[INFO] Received command: {command}")
            
            # This is the key part: update the global command
            # The rover_main_loop will see this and change behavior
            last_command = command 
            
            return jsonify({"status": "ok", "message": f"Command '{command}' received."})
        else:
            return jsonify({"status": "error", "message": "Invalid command."}), 400
            
    except Exception as e:
        print(f"[ERROR] Failed to handle command: {e}")
        return jsonify({"status": "error", "message": "Server error."}), 500

# --- MAIN ENTRY POINT ---

if __name__ == '__main__':
    try:
        # 1. Start the Rover's "Brain" in its own thread
        if ON_PI:
            rover_thread = threading.Thread(target=rover_main_loop, daemon=True)
            rover_thread.start()
        
        # 2. Start the Web Server
        print("\n" + "="*40)
        print(" PROJECT ARGUS SERVER IS LIVE")
        print(" Access dashboard at: http://127.0.0.1:5000")
        print("="*40 + "\n")
        app.run(host='0.0.0.0', port=5000, debug=False)

    except KeyboardInterrupt:
        print("\nShutting down...")
        if ON_PI:
            send_motor_command_to_pi(CMD_STOP)
            spi.close()

