import numpy as np


def reshape_rows(values, width):
    if width <= 0:
        return []
    data = np.asarray(values, dtype=float)
    if data.size % width:
        return []
    return np.round(data.reshape(-1, width), 6).tolist()


def block(matrix, rows, columns):
    data = np.asarray(matrix, dtype=float)
    if data.size == 0:
        return []
    return np.round(data[np.ix_(rows, columns)], 6).tolist()


def column_means(matrix):
    data = np.asarray(matrix, dtype=float)
    if data.size == 0:
        return []
    return np.round(data.mean(axis=0), 6).tolist()


def column_range(matrix, column):
    data = np.asarray(matrix, dtype=float)
    if data.size == 0:
        return 0.0
    return float(np.round(data[:, column].max() - data[:, column].min(), 6))
