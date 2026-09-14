"""
Complete Pipeline Runner for Ninapro DB2 Gesture Recognition
Author: Qoder
Date: 2025

This script runs the complete pipeline:
1. Data preprocessing
2. Model training
3. Export weights for ESP32

Usage: python run_pipeline.py
"""

import subprocess
import sys
import os


def run_script(script_name, extra_args=None):
    """Run a Python script and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {script_name}")
    print('='*60)
    
    cmd = [sys.executable, script_name]
    if extra_args:
        cmd.extend(extra_args)
    
    result = subprocess.run(
        cmd,
        capture_output=False,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: {script_name} failed with code {result.returncode}")
        return False
    
    return True


def main(data_dir=None, output_dir=None):
    """Run the complete pipeline.

    Args:
        data_dir: Directory containing Unity-collected gesture CSV files.
                  If None, uses '<script_dir>/data'.
        output_dir: Output directory for all generated files.
                    If None, uses the script's own directory.
    """
    script_dir = os.path.dirname(__file__)
    if data_dir is None:
        data_dir = os.path.join(script_dir, 'data')
    if output_dir is None:
        output_dir = script_dir
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║    Gesture Recognition Pipeline                          ║
    ║    For ESP32 Deployment                                  ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    print(f"Data directory: {data_dir}")
    print(f"Output directory: {output_dir}")
    
    # Change to script directory so sub-scripts are found
    os.chdir(script_dir)
    
    # Step 1: Preprocess data
    if not run_script('preprocess_data.py', ['--data-dir', data_dir, '--output-dir', output_dir]):
        return
    
    # Step 2: Train model
    data_path = os.path.join(output_dir, 'preprocessed_data.pkl')
    if not run_script('train_model.py', ['--data-path', data_path, '--output-dir', output_dir]):
        return
    
    # Step 3: Export weights
    if not run_script('export_weights.py', ['--output-dir', output_dir]):
        return
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║    Pipeline Complete!                                    ║
    ║                                                          ║
    ║    Generated files (in {output_dir}):
    ║    - preprocessed_data.pkl    : Preprocessed dataset     ║
    ║    - gesture_model.keras      : Trained Keras model      ║
    ║    - gesture_model.tflite     : TensorFlow Lite model    ║
    ║    - model.h                  : C header for ESP32       ║
    ║    - model_weights.h          : Trained weights          ║
    ║    - normalization_params.h   : Normalization params     ║
    ║                                                          ║
    ║    Next steps:                                           ║
    ║    1. Copy model.h to your ESP32 project                 ║
    ║    2. Use esp32_gesture_inference.cpp or                 ║
    ║       esp32_gesture_simple.ino as reference              ║
    ║    3. Flash to ESP32 and test!                           ║
    ╚══════════════════════════════════════════════════════════╝
    """)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Run complete training pipeline')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='Directory containing Unity-collected gesture CSV files')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for all generated files')
    args = parser.parse_args()
    main(data_dir=args.data_dir, output_dir=args.output_dir)
