"""
导出 ESP32 用 LDA 系数
Author: Qoder
Date: 2025

从 preprocessed_data.pkl 取双通道 RMS 特征拟合 LDA
输出 lda_model.bin 供回传 ESP32 写入 NVS，输出 C 头文件供编译期默认值
"""

import argparse
import os
import pickle
import struct

import numpy as np
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis

MAGIC = b'LDA1'                 # 包标记
BLOB_NAME = 'lda_model.bin'     # 二元包输出名
HEADER_NAME = 'lda_model_generated.h'  # C 头文件输出名
RMS_INDEXES = (1, 7)            # 双通道 RMS 在特征向量中的位置


def pack_blob(coef, intercept, mean, std):
    """按 标记+维度+系数+常数+均值+标准差 打包"""
    n_disc, n_feat = coef.shape
    return b''.join((
        MAGIC,
        struct.pack('<BB', n_feat, n_disc),
        coef.astype('<f4').tobytes(),
        intercept.astype('<f4').tobytes(),
        mean.astype('<f4').tobytes(),
        std.astype('<f4').tobytes(),
    ))


def write_header(coef, intercept, mean, std, output_path):
    """输出可直接替换 lda_model.h 的 C 头文件"""
    n_disc, n_feat = coef.shape

    def floats(values):
        return ', '.join(f'{v:.6f}f' for v in np.asarray(values).ravel())

    with open(output_path, 'w') as f:
        f.write('// Auto-generated LDA model for 2-channel EMG\n')
        f.write('#ifndef LDA_MODEL_GENERATED_H\n')
        f.write('#define LDA_MODEL_GENERATED_H\n\n')
        f.write(f'#define LDA_N_CLASSES {n_disc}\n')
        f.write(f'#define LDA_N_FEATURES {n_feat}\n\n')
        f.write(f'const float LDA_COEF[{n_disc}][{n_feat}] = {{\n')
        for row in coef:
            f.write(f'    {{{floats(row)}}},\n')
        f.write('};\n\n')
        f.write(f'const float LDA_INTERCEPT[{n_disc}] = {{{floats(intercept)}}};\n\n')
        f.write(f'const float FEATURE_MEAN[{n_feat}] = {{{floats(mean)}}};\n')
        f.write(f'const float FEATURE_STD[{n_feat}] = {{{floats(std)}}};\n\n')
        f.write('#endif\n')


def main(data_path=None, output_dir=None):
    """拟合 LDA 并导出二元包与头文件"""
    script_dir = os.path.dirname(__file__)
    if data_path is None:
        data_path = os.path.join(script_dir, 'preprocessed_data.pkl')
    if output_dir is None:
        output_dir = script_dir
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(data_path):
        print(f'export_lda|main|预处理数据不存在: {data_path}')
        return

    with open(data_path, 'rb') as f:
        data = pickle.load(f)

    X_train = data['X_train']
    y_train = data['y_train']
    if X_train.shape[1] <= max(RMS_INDEXES):
        print(f'export_lda|main|特征维度不足: {X_train.shape[1]}')
        return

    X = X_train[:, list(RMS_INDEXES)]
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    X_norm = (X - mean) / std

    lda = LinearDiscriminantAnalysis()
    lda.fit(X_norm, y_train)

    n_classes = len(lda.classes_)
    if list(lda.classes_) != list(range(n_classes)):
        print(f'export_lda|main|类别标签非连续整数: {list(lda.classes_)}')
        return

    coef = np.asarray(lda.coef_, dtype=np.float64)
    if coef.shape != (n_classes, len(RMS_INDEXES)):
        print(f'export_lda|main|系数形状不符: {coef.shape}')
        return

    blob = pack_blob(coef, lda.intercept_, mean, std)
    blob_path = os.path.join(output_dir, BLOB_NAME)
    with open(blob_path, 'wb') as f:
        f.write(blob)

    header_path = os.path.join(output_dir, HEADER_NAME)
    write_header(coef, lda.intercept_, mean, std, header_path)

    accuracy = lda.score(X_norm, y_train)
    print(f'export_lda|类别数={n_classes} 训练集准确率={accuracy:.4f}')
    print(f'export_lda|二元包 {len(blob)} 字节 -> {blob_path}')
    print(f'export_lda|头文件 -> {header_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export LDA coefficients for ESP32')
    parser.add_argument('--data-path', type=str, default=None,
                        help='Path to preprocessed_data.pkl')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for generated files')
    args = parser.parse_args()
    main(data_path=args.data_path, output_dir=args.output_dir)
