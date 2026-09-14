/*
 * ESP32 Gesture Recognition - Simplified Version
 * Author: Qoder
 * Date: 2025
 * 
 * This is a simplified version that doesn't require TensorFlow Lite.
 * It uses a custom lightweight neural network implementation.
 * 
 * Hardware Requirements:
 * - ESP32 DevKit
 * - 12-channel EMG acquisition circuit
 * - Sampling rate: 2000 Hz
 */

#include <Arduino.h>
#include <math.h>

// ============== Configuration ==============
#define NUM_CHANNELS 12
#define WINDOW_SIZE 200      // 100ms window at 2000Hz
#define STEP_SIZE 100        // 50% overlap
#define NUM_FEATURES 6       // MAV, RMS, WL, ZC, SSC, VAR
#define INPUT_SIZE (NUM_CHANNELS * NUM_FEATURES)  // 72
#define NUM_CLASSES 3

// EMG input pins (adjust according to your hardware)
const int emgPins[NUM_CHANNELS] = {
  34, 35, 32, 33, 25, 26,
  27, 14, 12, 13, 4, 2
};

// ============== Neural Network Configuration ==============
// Layer sizes
#define LAYER1_SIZE 32
#define LAYER2_SIZE 16
#define LAYER3_SIZE 8

// ============== Global Variables ==============
// EMG buffer
double emgBuffer[WINDOW_SIZE][NUM_CHANNELS];
int bufferIndex = 0;
bool bufferFull = false;

// Filter state
double filterState[NUM_CHANNELS][2] = {0};

// Neural network activations
double layer1[LAYER1_SIZE];
double layer2[LAYER2_SIZE];
double layer3[LAYER3_SIZE];
double output[NUM_CLASSES];

// ============== Model Weights (Placeholder) ==============
// These should be replaced with actual trained weights
// Format: weights are stored as flat arrays

// Layer 1: INPUT_SIZE -> LAYER1_SIZE
double W1[INPUT_SIZE * LAYER1_SIZE];  // Initialize in setup
double b1[LAYER1_SIZE];

// Layer 2: LAYER1_SIZE -> LAYER2_SIZE
double W2[LAYER1_SIZE * LAYER2_SIZE];
double b2[LAYER2_SIZE];

// Layer 3: LAYER2_SIZE -> LAYER3_SIZE
double W3[LAYER2_SIZE * LAYER3_SIZE];
double b3[LAYER3_SIZE];

// Output Layer: LAYER3_SIZE -> NUM_CLASSES
double W4[LAYER3_SIZE * NUM_CLASSES];
double b4[NUM_CLASSES];

// Normalization parameters (from training)
double featureMean[INPUT_SIZE];
double featureStd[INPUT_SIZE];

// ============== Function Prototypes ==============
void initializeModel();
void loadModelWeights();
double applyHighPassFilter(double input, int channel);
void processEMGSample();
void extractFeatures(double* features);
double relu(double x);
double softmax(double x, double* arr, int len);
void forwardPass(double* input);
int classifyGesture();
void printGesture(int gesture);

// ============== Setup ==============
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("========================================");
  Serial.println("ESP32 Gesture Recognition (Simple NN)");
  Serial.println("========================================");
  
  // Initialize EMG pins
  for (int i = 0; i < NUM_CHANNELS; i++) {
    pinMode(emgPins[i], INPUT);
  }
  
  // Initialize model
  initializeModel();
  loadModelWeights();
  
  Serial.println("System ready!");
  Serial.println("----------------------------------------\n");
}

// ============== Main Loop ==============
void loop() {
  static unsigned long lastSampleTime = 0;
  unsigned long currentTime = micros();
  
  // Sample at 2000Hz (every 500 microseconds)
  if (currentTime - lastSampleTime >= 500) {
    lastSampleTime = currentTime;
    
    processEMGSample();
    
    if (bufferFull) {
      int gesture = classifyGesture();
      printGesture(gesture);
      
      // Slide window (50% overlap)
      for (int i = 0; i < STEP_SIZE; i++) {
        for (int ch = 0; ch < NUM_CHANNELS; ch++) {
          emgBuffer[i][ch] = emgBuffer[i + STEP_SIZE][ch];
        }
      }
      bufferIndex = STEP_SIZE;
      bufferFull = false;
    }
  }
}

// ============== Model Initialization ==============
void initializeModel() {
  // Initialize normalization parameters
  // These should be replaced with values from your training data
  for (int i = 0; i < INPUT_SIZE; i++) {
    featureMean[i] = 0.0;
    featureStd[i] = 1.0;
  }
  
  // Initialize weights with small random values
  // In production, load these from trained model
  randomSeed(42);
  
  for (int i = 0; i < INPUT_SIZE * LAYER1_SIZE; i++) {
    W1[i] = ((double)random(1000) / 1000.0 - 0.5) * 0.1;
  }
  for (int i = 0; i < LAYER1_SIZE; i++) {
    b1[i] = 0.0;
  }
  
  for (int i = 0; i < LAYER1_SIZE * LAYER2_SIZE; i++) {
    W2[i] = ((double)random(1000) / 1000.0 - 0.5) * 0.1;
  }
  for (int i = 0; i < LAYER2_SIZE; i++) {
    b2[i] = 0.0;
  }
  
  for (int i = 0; i < LAYER2_SIZE * LAYER3_SIZE; i++) {
    W3[i] = ((double)random(1000) / 1000.0 - 0.5) * 0.1;
  }
  for (int i = 0; i < LAYER3_SIZE; i++) {
    b3[i] = 0.0;
  }
  
  for (int i = 0; i < LAYER3_SIZE * NUM_CLASSES; i++) {
    W4[i] = ((double)random(1000) / 1000.0 - 0.5) * 0.1;
  }
  for (int i = 0; i < NUM_CLASSES; i++) {
    b4[i] = 0.0;
  }
  
  Serial.println("Model initialized with random weights");
  Serial.println("NOTE: Replace with trained weights for actual use!");
}

void loadModelWeights() {
  // TODO: Load weights from SD card or flash memory
  // This function should read the trained weights from storage
  // and populate W1, b1, W2, b2, etc.
  
  // For now, we'll use the randomly initialized weights
  // In production, you would:
  // 1. Save trained weights to a file
  // 2. Read them here and assign to weight arrays
  
  Serial.println("Using default weights (replace with trained weights!)");
}

// ============== Signal Processing ==============
double applyHighPassFilter(double input, int channel) {
  // Simple first-order high-pass filter
  // y[n] = 0.9844*x[n] - 0.9844*x[n-1] + 0.9689*y[n-1]
  const double a = 0.9844;
  const double b = 0.9689;
  
  double x_n = input;
  double x_n1 = filterState[channel][0];
  double y_n1 = filterState[channel][1];
  
  double y_n = a * (x_n - x_n1) + b * y_n1;
  
  filterState[channel][0] = x_n;
  filterState[channel][1] = y_n;
  
  return y_n;
}

void processEMGSample() {
  for (int ch = 0; ch < NUM_CHANNELS; ch++) {
    // Read ADC (12-bit)
    int rawValue = analogRead(emgPins[ch]);
    
    // Convert to voltage and center at 0
    double voltage = (rawValue / 4095.0) * 3.3 - 1.65;
    
    // Apply filter
    double filtered = applyHighPassFilter(voltage, ch);
    
    // Store in buffer
    emgBuffer[bufferIndex][ch] = filtered;
  }
  
  bufferIndex++;
  
  if (bufferIndex >= WINDOW_SIZE) {
    bufferFull = true;
    bufferIndex = WINDOW_SIZE;
  }
}

// ============== Feature Extraction ==============
double computeMAV(double* data, int len) {
  double sum = 0;
  for (int i = 0; i < len; i++) {
    sum += abs(data[i]);
  }
  return sum / len;
}

double computeRMS(double* data, int len) {
  double sum = 0;
  for (int i = 0; i < len; i++) {
    sum += data[i] * data[i];
  }
  return sqrt(sum / len);
}

double computeWL(double* data, int len) {
  double wl = 0;
  for (int i = 1; i < len; i++) {
    wl += abs(data[i] - data[i-1]);
  }
  return wl;
}

int computeZC(double* data, int len) {
  int zc = 0;
  for (int i = 1; i < len; i++) {
    if ((data[i] * data[i-1]) < 0) {
      zc++;
    }
  }
  return zc;
}

int computeSSC(double* data, int len) {
  int ssc = 0;
  for (int i = 2; i < len; i++) {
    double diff1 = data[i-1] - data[i-2];
    double diff2 = data[i] - data[i-1];
    if ((diff1 * diff2) < 0) {
      ssc++;
    }
  }
  return ssc;
}

double computeVariance(double* data, int len) {
  double mean = 0;
  for (int i = 0; i < len; i++) {
    mean += data[i];
  }
  mean /= len;
  
  double var = 0;
  for (int i = 0; i < len; i++) {
    double diff = data[i] - mean;
    var += diff * diff;
  }
  return var / len;
}

void extractFeatures(double* features) {
  double channelData[WINDOW_SIZE];
  int featIdx = 0;
  
  for (int ch = 0; ch < NUM_CHANNELS; ch++) {
    // Extract channel data
    for (int i = 0; i < WINDOW_SIZE; i++) {
      channelData[i] = emgBuffer[i][ch];
    }
    
    // Compute features
    features[featIdx++] = computeMAV(channelData, WINDOW_SIZE);
    features[featIdx++] = computeRMS(channelData, WINDOW_SIZE);
    features[featIdx++] = computeWL(channelData, WINDOW_SIZE);
    features[featIdx++] = (double)computeZC(channelData, WINDOW_SIZE);
    features[featIdx++] = (double)computeSSC(channelData, WINDOW_SIZE);
    features[featIdx++] = computeVariance(channelData, WINDOW_SIZE);
  }
  
  // Normalize features
  for (int i = 0; i < INPUT_SIZE; i++) {
    features[i] = (features[i] - featureMean[i]) / featureStd[i];
  }
}

// ============== Neural Network ==============
double relu(double x) {
  return x > 0 ? x : 0;
}

double softmax(double x, double* arr, int len) {
  // Compute softmax for a single element
  double sum = 0;
  for (int i = 0; i < len; i++) {
    sum += exp(arr[i]);
  }
  return exp(x) / sum;
}

void forwardPass(double* input) {
  // Layer 1: INPUT_SIZE -> LAYER1_SIZE
  for (int i = 0; i < LAYER1_SIZE; i++) {
    layer1[i] = b1[i];
    for (int j = 0; j < INPUT_SIZE; j++) {
      layer1[i] += input[j] * W1[j * LAYER1_SIZE + i];
    }
    layer1[i] = relu(layer1[i]);
  }
  
  // Layer 2: LAYER1_SIZE -> LAYER2_SIZE
  for (int i = 0; i < LAYER2_SIZE; i++) {
    layer2[i] = b2[i];
    for (int j = 0; j < LAYER1_SIZE; j++) {
      layer2[i] += layer1[j] * W2[j * LAYER2_SIZE + i];
    }
    layer2[i] = relu(layer2[i]);
  }
  
  // Layer 3: LAYER2_SIZE -> LAYER3_SIZE
  for (int i = 0; i < LAYER3_SIZE; i++) {
    layer3[i] = b3[i];
    for (int j = 0; j < LAYER2_SIZE; j++) {
      layer3[i] += layer2[j] * W3[j * LAYER3_SIZE + i];
    }
    layer3[i] = relu(layer3[i]);
  }
  
  // Output Layer: LAYER3_SIZE -> NUM_CLASSES
  for (int i = 0; i < NUM_CLASSES; i++) {
    output[i] = b4[i];
    for (int j = 0; j < LAYER3_SIZE; j++) {
      output[i] += layer3[j] * W4[j * NUM_CLASSES + i];
    }
  }
  
  // Apply softmax to output
  double sum = 0;
  for (int i = 0; i < NUM_CLASSES; i++) {
    output[i] = exp(output[i]);
    sum += output[i];
  }
  for (int i = 0; i < NUM_CLASSES; i++) {
    output[i] /= sum;
  }
}

// ============== Classification ==============
int classifyGesture() {
  double features[INPUT_SIZE];
  extractFeatures(features);
  
  // Forward pass through neural network
  forwardPass(features);
  
  // Find class with highest probability
  int maxIdx = 0;
  double maxProb = output[0];
  for (int i = 1; i < NUM_CLASSES; i++) {
    if (output[i] > maxProb) {
      maxProb = output[i];
      maxIdx = i;
    }
  }
  
  return maxIdx;
}

void printGesture(int gesture) {
  const char* gestureNames[] = {"Gesture 0", "Gesture 1", "Gesture 2"};
  
  Serial.print("Detected: ");
  Serial.print(gestureNames[gesture]);
  Serial.print(" (Confidence: ");
  Serial.print(output[gesture] * 100, 1);
  Serial.println("%)");
}

// ============== Utility Functions ==============
/*
 * To use trained weights:
 * 
 * 1. After training with train_model.py, you'll get model_weights.npz
 * 2. Convert the weights to C arrays using a Python script
 * 3. Include them in this file or load from SD card
 * 
 * Example Python conversion:
 * 
 * import numpy as np
 * weights = np.load('model_weights.npz')
 * 
 * # Print weights as C arrays
 * print("double W1[] = {", ",".join(map(str, weights['layer_0_weights'].flatten())), "};")
 * print("double b1[] = {", ",".join(map(str, weights['layer_0_bias'])), "};")
 * # ... repeat for other layers
 */
