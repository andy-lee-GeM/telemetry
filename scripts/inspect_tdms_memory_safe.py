#!/usr/bin/env python3
"""
TDMS Inspector - Memory-safe version for large files
"""

import nptdms
import numpy as np
import sys
from pathlib import Path

def inspect_tdms_file_memory_safe(file_path, max_samples_per_channel=1000):
    """Inspect TDMS file structure and sensor properties with memory optimization"""
    print(f"🔍 Inspecting TDMS file: {file_path}")
    print("=" * 80)
    
    try:
        # Open TDMS file
        tdms_file = nptdms.TdmsFile(file_path)
        
        # File-level properties
        print(f"📄 FILE PROPERTIES:")
        if hasattr(tdms_file, 'properties') and tdms_file.properties:
            for key, value in tdms_file.properties.items():
                print(f"   {key}: {value}")
        else:
            print("   No file properties found")
        
        print("\n" + "=" * 80)
        
        # Inspect each group
        for group in tdms_file.groups():
            print(f"\n�� GROUP: {group.name}")
            print("-" * 40)
            
            # Group properties
            if hasattr(group, 'properties') and group.properties:
                print("   Group Properties:")
                for key, value in group.properties.items():
                    print(f"     {key}: {value}")
            
            # Inspect each channel in the group
            for channel in group.channels():
                print(f"\n   📊 CHANNEL: {channel.name}")
                
                # Channel properties
                if hasattr(channel, 'properties') and channel.properties:
                    print("      Properties:")
                    for key, value in channel.properties.items():
                        print(f"        {key}: {value}")
                
                # Data information - with memory safety
                if hasattr(channel, 'data') and channel.data is not None:
                    data = channel.data
                    sample_count = len(data)
                    print(f"      Data Info:")
                    print(f"        Sample count: {sample_count:,}")
                    print(f"        Data type: {data.dtype}")
                    
                    # Handle different data types with sampling
                    if np.issubdtype(data.dtype, np.number):
                        # For large datasets, sample for statistics
                        if sample_count > max_samples_per_channel:
                            # Sample evenly across the dataset
                            step = sample_count // max_samples_per_channel
                            sampled_data = data[::step]
                            print(f"        ⚠️  Large dataset - using {len(sampled_data):,} samples for statistics")
                        else:
                            sampled_data = data
                        
                        # Calculate statistics on sampled data
                        print(f"        Min value: {np.min(sampled_data):.6f}")
                        print(f"        Max value: {np.max(sampled_data):.6f}")
                        print(f"        Mean: {np.mean(sampled_data):.6f}")
                        print(f"        Std Dev: {np.std(sampled_data):.6f}")
                        
                        # Show first and last few values
                        print(f"        First 5 values: {data[:5]}")
                        if sample_count > 5:
                            print(f"        Last 5 values: {data[-5:]}")
                            
                    elif np.issubdtype(data.dtype, np.datetime64):
                        # DateTime data
                        print(f"        Min time: {np.min(data)}")
                        print(f"        Max time: {np.max(data)}")
                        print(f"        First 5 values: {data[:5]}")
                        if sample_count > 5:
                            print(f"        Last 5 values: {data[-5:]}")
                    else:
                        # String or other data
                        print(f"        Sample values: {data[:3] if len(data) > 3 else data}")
                        print(f"        First 5 values: {data[:5]}")
                        if sample_count > 5:
                            print(f"        Last 5 values: {data[-5:]}")
                else:
                    print(f"      Data Info: No data or empty")
        
        print("\n" + "=" * 80)
        
        # Summary
        total_groups = len(list(tdms_file.groups()))
        total_channels = sum(len(list(group.channels())) for group in tdms_file.groups())
        
        print(f"�� SUMMARY:")
        print(f"   Total groups: {total_groups}")
        print(f"   Total channels: {total_channels}")
        
        # List all channel names for easy reference
        print(f"\n📝 ALL CHANNEL NAMES:")
        for group in tdms_file.groups():
            for channel in group.channels():
                print(f"   {group.name} → {channel.name}")
                
    except MemoryError:
        print("❌ Memory Error: File is too large to load completely")
        print("💡 Try using the memory-safe processing client instead:")
        print("   python -c \"from clients.cdaq.cdaq_client import CDAQClient; client = CDAQClient(); client.process_tdms_file('your_file.tdms')\"")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error inspecting TDMS file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_tdms_memory_safe.py <tdms_file_path>")
        print("Example: python inspect_tdms_memory_safe.py data/FRIGIDAIRE-2025-02-19-19-55-25.tdms")
        sys.exit(1)
    
    tdms_path = sys.argv[1]
    
    try:
        inspect_tdms_file_memory_safe(tdms_path)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {tdms_path}")
        sys.exit(1) 