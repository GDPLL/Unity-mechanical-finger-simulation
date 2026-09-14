"""
Ninapro DB2 sEMG Data Preprocessing for ESP32 Gesture Recognition
Author: Qoder
Date: 2025

This script preprocesses sEMG data for training a lightweight gesture recognition model
designed to run on ESP32 microcontrollers.
"""

import numpy as np
import pandas as pd
from scipy import signal
from scipy.signal import butter, filtfilt, iirnotch
import os
import pickle
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split

# Configuration
SAMPLING_RATE = 2000  # 采样率 (Hz)
WINDOW_SIZE = 200     # 100ms window
STEP_SIZE = 100       # 50% overlap
NUM_CHANNELS = 2      # 双通道肌电信号（Unity 采集 rest1/rest2）

# Filter parameters
LOWCUT = 10           # High-pass filter cutoff (Hz)
HIGHCUT = 500         # Low-pass filter cutoff (Hz)
NOTCH_FREQ = 50       # Notch filter for power line interference (Hz)


def butter_bandpass(lowcut, highcut, fs, order=4):
    """Design Butterworth bandpass filter."""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a


def apply_bandpass_filter(data, lowcut=10, highcut=500, fs=2000, order=4):
    """Apply bandpass filter to remove noise."""
    b, a = butter_bandpass(lowcut, highcut, fs, order)
    filtered_data = filtfilt(b, a, data, axis=0)
    return filtered_data


def apply_notch_filter(data, freq=50, fs=2000, quality=30):
    """Apply notch filter to remove power line interference."""
    b, a = iirnotch(freq, quality, fs)
    filtered_data = filtfilt(b, a, data, axis=0)
    return filtered_data


def normalize_data(data, method='standard'):
    """
    Normalize EMG data.
    method: 'standard' (z-score), 'minmax', 'maxabs'
    """
    if method == 'standard':
        mean = np.mean(data, axis=0)
        std = np.std(data, axis=0)
        std[std == 0] = 1  # Avoid division by zero
        return (data - mean) / std
    elif method == 'minmax':
        min_val = np.min(data, axis=0)
        max_val = np.max(data, axis=0)
        range_val = max_val - min_val
        range_val[range_val == 0] = 1
        return (data - min_val) / range_val
    elif method == 'maxabs':
        max_abs = np.max(np.abs(data), axis=0)
        max_abs[max_abs == 0] = 1
        return data / max_abs
    return data


def extract_features(window):
    """
    Extract time-domain features from EMG window.
    Optimized for ESP32 (lightweight features).
    """
    features = []
    
    for ch in range(window.shape[1]):
        channel_data = window[:, ch]
        
        # Mean Absolute Value (MAV) - most important feature
        mav = np.mean(np.abs(channel_data))
        features.append(mav)
        
        # Root Mean Square (RMS)
        rms = np.sqrt(np.mean(channel_data ** 2))
        features.append(rms)
        
        # Waveform Length (WL)
        wl = np.sum(np.abs(np.diff(channel_data)))
        features.append(wl)
        
        # Zero Crossing (ZC) - simplified for ESP32
        zc = np.sum(((channel_data[:-1] * channel_data[1:]) < 0))
        features.append(zc)
        
        # Slope Sign Changes (SSC) - simplified
        diff = np.diff(channel_data)
        ssc = np.sum((diff[:-1] * diff[1:]) < 0)
        features.append(ssc)
        
        # Variance
        var = np.var(channel_data)
        features.append(var)
    
    return np.array(features)


def segment_data(data, window_size=200, step_size=100):
    """
    Segment continuous EMG data into overlapping windows.
    """
    n_samples = data.shape[0]
    n_windows = (n_samples - window_size) // step_size + 1
    
    windows = []
    for i in range(n_windows):
        start = i * step_size
        end = start + window_size
        if end <= n_samples:
            windows.append(data[start:end, :])
    
    return windows


def load_and_preprocess_file(filepath, label):
    """
    Load a CSV file and preprocess the data.
    """
    print(f"Processing {filepath}...")
    
    # Load data
    df = pd.read_csv(filepath)
    data = df.values
    
    print(f"  Original shape: {data.shape}")
    
    # Apply bandpass filter
    data_filtered = apply_bandpass_filter(data, LOWCUT, HIGHCUT, SAMPLING_RATE)
    
    # Apply notch filter to remove 50Hz power line interference
    data_filtered = apply_notch_filter(data_filtered, NOTCH_FREQ, SAMPLING_RATE)
    
    # Normalize
    data_normalized = normalize_data(data_filtered, method='standard')
    
    # Segment into windows
    windows = segment_data(data_normalized, WINDOW_SIZE, STEP_SIZE)
    
    print(f"  Generated {len(windows)} windows")
    
    # Extract features from each window
    features = []
    for window in windows:
        feat = extract_features(window)
        features.append(feat)
    
    features = np.array(features)
    labels = np.full(len(features), label)
    
    return features, labels


def main(data_dir=None, output_dir=None):
    """Main preprocessing pipeline.

    Args:
        data_dir: Directory containing the Unity-collected gesture CSV files.
                  Each CSV = one gesture sample (2 columns: emg_col0, emg_col1).
                  Labels are assigned by file name order: 0, 1, 2, ...
                  If None, uses '<script_dir>/data'.
        output_dir: Output directory for preprocessed data.
                    If None, uses the script's own directory.
    """
    script_dir = os.path.dirname(__file__)
    if data_dir is None:
        data_dir = os.path.join(script_dir, 'data')
    if output_dir is None:
        output_dir = script_dir
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # 扫描 data 目录下所有 CSV，按文件名排序，依次分配标签 0,1,2,...
    csv_files = sorted(
        f for f in os.listdir(data_dir) if f.lower().endswith('.csv')
    )

    if not csv_files:
        print(f"Warning: {data_dir} 下没有 CSV 数据文件，请先在 Unity 中采集数据")
        return

    print(f"在 {data_dir} 找到 {len(csv_files)} 个 CSV 数据文件")
    all_features = []
    all_labels = []

    for idx, filename in enumerate(csv_files):
        filepath = os.path.join(data_dir, filename)
        label = idx  # 标签 = 文件顺序
        print(f"  标签 {label} <- {filename}")
        features, labels = load_and_preprocess_file(filepath, label)
        all_features.append(features)
        all_labels.append(labels)

    # Combine all data
    X = np.vstack(all_features)
    y = np.concatenate(all_labels)

    num_channels = X.shape[1] // 6  # 每通道 6 特征
    print(f"\nTotal samples: {X.shape[0]}")
    print(f"Feature dimension: {X.shape[1]} (通道数={num_channels})")
    print(f"Number of classes: {len(np.unique(y))}")
    
    # Split into train and test sets
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Further split training set for validation
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
    )
    
    print(f"\nTrain set: {X_train.shape[0]} samples")
    print(f"Validation set: {X_val.shape[0]} samples")
    print(f"Test set: {X_test.shape[0]} samples")
    
    # Save preprocessed data (use output_dir from parameter)
    data_dict = {
        'X_train': X_train,
        'X_val': X_val,
        'X_test': X_test,
        'y_train': y_train,
        'y_val': y_val,
        'y_test': y_test,
        'feature_names': ['MAV', 'RMS', 'WL', 'ZC', 'SSC', 'VAR'] * num_channels,
        'num_channels': num_channels,
        'window_size': WINDOW_SIZE,
        'sampling_rate': SAMPLING_RATE
    }
    
    output_path = os.path.join(output_dir, 'preprocessed_data.pkl')
    with open(output_path, 'wb') as f:
        pickle.dump(data_dict, f)
    
    print(f"\nPreprocessed data saved to: {output_path}")
    
    # Also save as numpy arrays for easy loading
    np.save(os.path.join(output_dir, 'X_train.npy'), X_train)
    np.save(os.path.join(output_dir, 'X_val.npy'), X_val)
    np.save(os.path.join(output_dir, 'X_test.npy'), X_test)
    np.save(os.path.join(output_dir, 'y_train.npy'), y_train)
    np.save(os.path.join(output_dir, 'y_val.npy'), y_val)
    np.save(os.path.join(output_dir, 'y_test.npy'), y_test)
    
    print("Individual numpy arrays saved!")
    
    return data_dict


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Preprocess gesture data')
    parser.add_argument('--data-dir', type=str, default=None,
                        help='Directory containing Unity-collected gesture CSV files')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for preprocessed data')
    args = parser.parse_args()
    main(data_dir=args.data_dir, output_dir=args.output_dir)
