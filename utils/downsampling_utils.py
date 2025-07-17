#!/usr/bin/env python3
"""
Simple downsampling utilities for telemetry data
Explicit method selection - no automatic suggestions
"""

import numpy as np
from typing import Tuple

def calculate_max_samples_from_hz(target_hz: float, duration_hours: float) -> int:
    """
    Calculate maximum samples based on target Hz and duration
    
    Args:
        target_hz: Target sample rate in Hz
        duration_hours: Maximum duration in hours
    
    Returns:
        Maximum number of samples to keep per channel
    """
    return int(target_hz * duration_hours * 3600)

def downsample(data: np.ndarray, target_samples: int, method: str) -> np.ndarray:
    """
    Downsample data using specified method
    
    Args:
        data: Input data array
        target_samples: Target number of samples
        method: 'decimation' or 'averaging'
    
    Returns:
        Downsampled data array
    """
    if len(data) <= target_samples:
        return data
    
    if method == 'decimation':
        return _downsample_decimate(data, target_samples)
    elif method == 'averaging':
        return _downsample_average(data, target_samples)
    else:
        raise ValueError(f"Unknown downsampling method: {method}. Use 'decimation' or 'averaging'")

def _downsample_decimate(data: np.ndarray, target_samples: int) -> np.ndarray:
    """
    Decimate by taking every Nth sample
    Fast but can cause aliasing
    """
    step = len(data) // target_samples
    return data[::step][:target_samples]

def _downsample_average(data: np.ndarray, target_samples: int) -> np.ndarray:
    """
    Downsample by averaging blocks of samples
    Slower but reduces aliasing
    """
    block_size = len(data) // target_samples
    trimmed_length = (len(data) // block_size) * block_size
    trimmed_data = data[:trimmed_length]
    blocks = trimmed_data.reshape(-1, block_size)
    return np.mean(blocks, axis=1)

def get_downsample_info(original_samples: int, target_samples: int, method: str) -> dict:
    """
    Get information about downsampling without processing data
    
    Args:
        original_samples: Original number of samples
        target_samples: Target number of samples  
        method: 'decimation' or 'averaging'
    
    Returns:
        Dictionary with downsampling information
    """
    if original_samples <= target_samples:
        return {
            'method': 'none',
            'reduction_ratio': 1.0,
            'output_samples': original_samples,
            'step_size': 1
        }
    
    if method == 'decimation':
        step = original_samples // target_samples
        output_samples = min(target_samples, original_samples // step)
        return {
            'method': 'decimation',
            'reduction_ratio': output_samples / original_samples,
            'output_samples': output_samples,
            'step_size': step
        }
    
    elif method == 'averaging':
        block_size = original_samples // target_samples
        output_samples = original_samples // block_size
        return {
            'method': 'averaging',
            'reduction_ratio': output_samples / original_samples,
            'output_samples': output_samples,
            'block_size': block_size
        }
    
    else:
        raise ValueError(f"Unknown method: {method}") 