"""
Train Lightweight Neural Network for ESP32 Gesture Recognition
Author: Qoder
Date: 2025

This script trains a compact neural network suitable for deployment on ESP32.
The model is converted to TensorFlow Lite format for embedded deployment.
"""

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import os
import pickle
import json

# Configuration
NUM_CLASSES = 3      # 手势类别数（由数据动态决定）
INPUT_DIM = 12       # 双通道 * 6 特征 = 12（由数据动态决定）
EPOCHS = 100
BATCH_SIZE = 32
LEARNING_RATE = 0.001


def create_lightweight_model(input_dim, num_classes):
    """
    Create a lightweight neural network optimized for ESP32.
    
    Architecture:
    - Input: input_dim features (channels * 6 features)
    - Hidden layers: Small dense layers with ReLU activation
    - Output: Softmax for classification
    """
    model = keras.Sequential([
        # Input layer
        layers.Input(shape=(input_dim,)),
        
        # First hidden layer - compact
        layers.Dense(32, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.2),
        
        # Second hidden layer
        layers.Dense(16, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.2),
        
        # Third hidden layer - very compact for ESP32
        layers.Dense(8, activation='relu'),
        
        # Output layer
        layers.Dense(num_classes, activation='softmax')
    ])
    
    return model


def create_tiny_model(input_dim, num_classes):
    """
    Create an even smaller model for very constrained ESP32 devices.
    """
    model = keras.Sequential([
        layers.Input(shape=(input_dim,)),
        layers.Dense(16, activation='relu'),
        layers.Dense(8, activation='relu'),
        layers.Dense(num_classes, activation='softmax')
    ])
    
    return model


def train_model(X_train, y_train, X_val, y_val, input_dim=None, num_classes=None, model_type='lightweight'):
    """Train the gesture recognition model.

    Args:
        input_dim: Feature dimension. If None, derived from X_train.
        num_classes: Number of gesture classes. If None, derived from labels.
    """
    if input_dim is None:
        input_dim = X_train.shape[1]
    if num_classes is None:
        num_classes = len(np.unique(np.concatenate([y_train, y_val])))

    # Convert labels to categorical
    y_train_cat = keras.utils.to_categorical(y_train, num_classes)
    y_val_cat = keras.utils.to_categorical(y_val, num_classes)
    
    # Create model
    if model_type == 'lightweight':
        model = create_lightweight_model(input_dim, num_classes)
    else:
        model = create_tiny_model(input_dim, num_classes)
    
    # Compile model
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )
    
    # Print model summary
    model.summary()
    
    # Callbacks
    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=15,
            restore_best_weights=True
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=5,
            min_lr=1e-6
        )
    ]
    
    # Train
    print("\nStarting training...")
    history = model.fit(
        X_train, y_train_cat,
        validation_data=(X_val, y_val_cat),
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=callbacks,
        verbose=1
    )
    
    return model, history


def evaluate_model(model, X_test, y_test, num_classes=None):
    """Evaluate model performance."""
    if num_classes is None:
        num_classes = len(np.unique(y_test))
    y_test_cat = keras.utils.to_categorical(y_test, num_classes)
    
    loss, accuracy = model.evaluate(X_test, y_test_cat, verbose=0)
    print(f"\nTest Loss: {loss:.4f}")
    print(f"Test Accuracy: {accuracy:.4f}")
    
    # Get predictions
    y_pred = model.predict(X_test, verbose=0)
    y_pred_classes = np.argmax(y_pred, axis=1)
    
    # Classification report
    from sklearn.metrics import classification_report, confusion_matrix
    
    target_names = [f'Gesture {i}' for i in range(num_classes)]
    
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred_classes, target_names=target_names))
    
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_test, y_pred_classes))
    
    return accuracy


def convert_to_tflite(model, output_path, quantize=True):
    """
    Convert Keras model to TensorFlow Lite format.
    
    Args:
        model: Keras model
        output_path: Path to save TFLite model
        quantize: Whether to apply quantization for smaller size
    """
    print("\nConverting to TensorFlow Lite...")
    
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    
    if quantize:
        # Apply post-training quantization
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
        print("  Using float16 quantization")
    
    tflite_model = converter.convert()
    
    # Save the model
    with open(output_path, 'wb') as f:
        f.write(tflite_model)
    
    model_size_kb = len(tflite_model) / 1024
    print(f"  TFLite model size: {model_size_kb:.2f} KB")
    print(f"  Saved to: {output_path}")
    
    return tflite_model


def export_model_for_esp32(model, output_dir):
    """
    Export model in formats suitable for ESP32 deployment.
    
    Creates:
    1. TensorFlow Lite model (.tflite)
    2. C header file with model weights (model.h)
    3. JSON file with model architecture
    """
    print("\nExporting model for ESP32...")
    
    # 1. Save as TensorFlow Lite
    tflite_path = os.path.join(output_dir, 'gesture_model.tflite')
    tflite_model = convert_to_tflite(model, tflite_path, quantize=True)
    
    # 2. Convert to C array for embedding in ESP32 code
    c_header_path = os.path.join(output_dir, 'model.h')
    
    with open(c_header_path, 'w') as f:
        f.write("/*\n")
        f.write(" * Gesture Recognition Model for ESP32\n")
        f.write(" * Auto-generated by train_model.py\n")
        f.write(" */\n\n")
        f.write("#ifndef GESTURE_MODEL_H\n")
        f.write("#define GESTURE_MODEL_H\n\n")
        f.write(f"#define MODEL_SIZE {len(tflite_model)}\n\n")
        f.write("const unsigned char gesture_model[] = {\n  ")
        
        # Write hex values
        for i, byte in enumerate(tflite_model):
            if i > 0:
                if i % 12 == 0:
                    f.write(",\n  ")
                else:
                    f.write(", ")
            f.write(f"0x{byte:02x}")
        
        f.write("\n};\n\n")
        f.write("#endif // GESTURE_MODEL_H\n")
    
    print(f"  C header saved to: {c_header_path}")
    
    # 3. Save model architecture as JSON
    model_json = model.to_json()
    json_path = os.path.join(output_dir, 'model_architecture.json')
    with open(json_path, 'w') as f:
        json.dump(json.loads(model_json), f, indent=2)
    print(f"  Model architecture saved to: {json_path}")
    
    # 4. Save weights separately (for custom implementation)
    weights_path = os.path.join(output_dir, 'model_weights.npz')
    weights = {}
    for i, layer in enumerate(model.layers):
        layer_weights = layer.get_weights()
        if layer_weights:
            weights[f'layer_{i}_weights'] = layer_weights[0]
            weights[f'layer_{i}_bias'] = layer_weights[1]
    np.savez(weights_path, **weights)
    print(f"  Model weights saved to: {weights_path}")
    
    return tflite_model


def main(data_path=None, output_dir=None):
    """Main training pipeline.
    
    Args:
        data_path: Path to preprocessed_data.pkl. If None, uses script directory.
        output_dir: Output directory for trained model files. If None, uses script directory.
    """
    script_dir = os.path.dirname(__file__)
    if data_path is None:
        data_path = os.path.join(script_dir, 'preprocessed_data.pkl')
    if output_dir is None:
        output_dir = script_dir
    os.makedirs(output_dir, exist_ok=True)
    
    if not os.path.exists(data_path):
        print("Error: Preprocessed data not found!")
        print(f"Expected at: {data_path}")
        print("Please run preprocess_data.py first.")
        return
    
    print("Loading preprocessed data...")
    with open(data_path, 'rb') as f:
        data = pickle.load(f)
    
    X_train = data['X_train']
    X_val = data['X_val']
    X_test = data['X_test']
    y_train = data['y_train']
    y_val = data['y_val']
    y_test = data['y_test']
    
    print(f"Training samples: {X_train.shape[0]}")
    print(f"Validation samples: {X_val.shape[0]}")
    print(f"Test samples: {X_test.shape[0]}")
    print(f"Feature dimension: {X_train.shape[1]}")

    # 由数据动态推导输入维度与类别数
    input_dim = int(X_train.shape[1])
    num_classes = int(len(np.unique(np.concatenate([y_train, y_val, y_test]))))
    print(f"Input dimension: {input_dim}, Classes: {num_classes}")

    # Train model
    model, history = train_model(
        X_train, y_train, X_val, y_val,
        input_dim=input_dim, num_classes=num_classes, model_type='lightweight'
    )
    
    # Evaluate
    accuracy = evaluate_model(model, X_test, y_test, num_classes=num_classes)
    
    # Save Keras model
    keras_path = os.path.join(output_dir, 'gesture_model.keras')
    model.save(keras_path)
    print(f"\nKeras model saved to: {keras_path}")
    
    # Export for ESP32
    export_model_for_esp32(model, output_dir)
    
    print("\n" + "="*50)
    print("Training complete!")
    print(f"Final test accuracy: {accuracy:.4f}")
    print("="*50)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Train gesture recognition model')
    parser.add_argument('--data-path', type=str, default=None,
                        help='Path to preprocessed_data.pkl')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for model files')
    args = parser.parse_args()
    main(data_path=args.data_path, output_dir=args.output_dir)
