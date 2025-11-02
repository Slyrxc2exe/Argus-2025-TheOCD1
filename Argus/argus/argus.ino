/**
 * PROJECT ARGUS - Arduino Firmware (v2 - Simplified)
 * ----------------------------------------------------
 * This code runs on the Arduino Uno.
 * It has two jobs:
 * 1. Main Loop: Continuously reads Ultrasonic (Distance) and
 * a voltage divider (Battery Level).
 * 2. SPI Interrupt: Instantly responds to commands or data requests
 * from the Raspberry Pi (the "Brain").
 */

// --- LIBRARIES ---
#include <SPI.h>

// --- PIN DEFINITIONS (*** YOU MUST CHANGE THESE TO MATCH YOUR WIRING ***) ---

// L298N Motor Driver Pins
#define MOTOR_ENA 5   // Left motor speed (PWM)
#define MOTOR_IN1 4   // Left motor direction
#define MOTOR_IN2 3   // Left motor direction
#define MOTOR_ENB 6   // Right motor speed (PWM)
#define MOTOR_IN3 7   // Right motor direction
#define MOTOR_IN4 8   // Right motor direction

// HC-SR04 Ultrasonic Sensor Pins
#define TRIG_PIN 9
#define ECHO_PIN 10

// Battery Voltage Sensor Pin
// (Connect to a voltage divider on Analog Pin 0)
#define BATT_PIN A0

// --- SPI COMMANDS (MUST match Python app.py) ---
#define CMD_STOP        0x00
#define CMD_FORWARD     0x01
#define CMD_REVERSE     0x02
#define CMD_TURN_LEFT   0x03
#define CMD_TURN_RIGHT  0x04
#define CMD_GET_SENSOR_DATA 0x10

// --- GLOBAL VARIABLES ---
volatile byte command = 0; // Command received from Pi

// This struct holds our sensor data.
// 'h' (short) = 2 bytes for distance
// 'b' (byte)  = 1 byte for battery level (0-100%)
// Total size: 3 bytes
struct SensorData {
  short distance;
  byte battery_level;
};
volatile SensorData sensorData;

void setup() {
  // --- Pin Modes ---
  pinMode(MOTOR_ENA, OUTPUT);
  pinMode(MOTOR_IN1, OUTPUT);
  pinMode(MOTOR_IN2, OUTPUT);
  pinMode(MOTOR_ENB, OUTPUT);
  pinMode(MOTOR_IN3, OUTPUT);
  pinMode(MOTOR_IN4, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(BATT_PIN, INPUT);

  // Stop motors on startup
  stopMotors();

  // --- SPI Setup ---
  pinMode(MISO, OUTPUT);  // Set MISO (Master In Slave Out) as OUTPUT
  SPCR |= _BV(SPE);     // Enable SPI
  SPCR |= _BV(SPIE);    // Enable SPI Interrupt
  
  // Prepare initial sensor data
  sensorData.distance = 0;
  sensorData.battery_level = 0;
}

// --- MAIN LOOP (Runs constantly) ---
void loop() {
  // 1. Read Sensors
  sensorData.distance = readUltrasonic();
  sensorData.battery_level = readBattery();

  // 2. Execute Motor Command (if one was received via SPI)
  executeMotorCommand(command);

  // Reset command so it only executes once
  command = 0; 
  
  delay(100); // Read sensors 10 times a second
}

// --- SPI INTERRUPT SERVICE ROUTINE (ISR) ---
// This function is called AUTOMATICALLY when the Pi sends SPI data.
ISR(SPI_STC_vect) {
  byte receivedByte = SPDR; // Read the byte from the Pi

  if (receivedByte == CMD_GET_SENSOR_DATA) {
    // If Pi requests data, send the 3-byte data packet
    // This is a "shift register" style transfer
    SPDR = (sensorData.distance >> 8) & 0xFF; // Send Distance high byte
    while (!(SPSR & _BV(SPIF)));
    SPDR = sensorData.distance & 0xFF;        // Send Distance low byte
    while (!(SPSR & _BV(SPIF)));
    SPDR = sensorData.battery_level;          // Send Battery byte
  }
  else {
    // Otherwise, it's a motor command
    command = receivedByte;
    SPDR = 0xFF; // Acknowledge byte (0xFF means "OK")
  }
}

// --- SENSOR HELPER FUNCTIONS ---

short readUltrasonic() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH, 25000); // 25ms timeout
  
  // Calculate distance in cm
  // 343 m/s = 0.0343 cm/us. Divide by 2 for round trip.
  return (short)(duration * 0.0343 / 2.0);
}

byte readBattery() {
  // Read the analog value (0-1023)
  int sensorValue = analogRead(BATT_PIN);
  
  // --- This 'map' is an EXAMPLE. You MUST change it. ---
  // You need to measure:
  // 1. The analogRead() value when your battery is FULL (e.g., 850)
  // 2. The analogRead() value when your battery is EMPTY (e.g., 600)
  // Then, replace 600 and 850 with your measured values.
  long batteryPercent = map(sensorValue, 600, 850, 0, 100);
  
  // Constrain the value between 0 and 100
  return (byte)constrain(batteryPercent, 0, 100);
}

// --- MOTOR HELPER FUNCTIONS ---

void executeMotorCommand(byte cmd) {
  switch (cmd) {
    case CMD_FORWARD:
      goForward();
      break;
    case CMD_REVERSE:
      goReverse();
      break;
    case CMD_TURN_LEFT:
      turnLeft();
      break;
    case CMD_TURN_RIGHT:
      turnRight();
      break;
    case CMD_STOP:
      stopMotors();
      break;
    // Any other command (like 0) does nothing
  }
}

void goForward() {
  digitalWrite(MOTOR_IN1, HIGH);
  digitalWrite(MOTOR_IN2, LOW);
  digitalWrite(MOTOR_IN3, HIGH);
  digitalWrite(MOTOR_IN4, LOW);
  analogWrite(MOTOR_ENA, 200); // 200/255 speed
  analogWrite(MOTOR_ENB, 200);
}

void goReverse() {
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, HIGH);
  digitalWrite(MOTOR_IN3, LOW);
  digitalWrite(MOTOR_IN4, HIGH);
  analogWrite(MOTOR_ENA, 150);
  analogWrite(MOTOR_ENB, 150);
}

void turnLeft() {
  digitalWrite(MOTOR_IN1, LOW);   // Left motor reverse
  digitalWrite(MOTOR_IN2, HIGH);
  digitalWrite(MOTOR_IN3, HIGH);  // Right motor forward
  digitalWrite(MOTOR_IN4, LOW);
  analogWrite(MOTOR_ENA, 180);
  analogWrite(MOTOR_ENB, 180);
}

void turnRight() {
  digitalWrite(MOTOR_IN1, HIGH);  // Left motor forward
  digitalWrite(MOTOR_IN2, LOW);
  digitalWrite(MOTOR_IN3, LOW);   // Right motor reverse
  digitalWrite(MOTOR_IN4, HIGH);
  analogWrite(MOTOR_ENA, 180);
  analogWrite(MOTOR_ENB, 180);
}

void stopMotors() {
  digitalWrite(MOTOR_IN1, LOW);
  digitalWrite(MOTOR_IN2, LOW);
  digitalWrite(MOTOR_IN3, LOW);
  digitalWrite(MOTOR_IN4, LOW);
  analogWrite(MOTOR_ENA, 0);
  analogWrite(MOTOR_ENB, 0);
}

