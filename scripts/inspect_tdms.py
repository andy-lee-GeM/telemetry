#!/usr/bin/env python3
"""
TDMS Inspector - Manually inspect sensors and properties
"""

import nptdms
import numpy as np

def inspect_tdms_file(file_path):
    """Inspect TDMS file structure and sensor properties"""
    print(f"🔍 Inspecting TDMS file: {file_path}")
    print("=" * 80)
    
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
        print(f"\n📁 GROUP: {group.name}")
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
            
            # Data information
            if hasattr(channel, 'data') and channel.data is not None:
                data = channel.data
                print(f"      Data Info:")
                print(f"        Sample count: {len(data):,}")
                print(f"        Data type: {data.dtype}")
                
                # Handle different data types
                if np.issubdtype(data.dtype, np.number):
                    # Numeric data
                    print(f"        Min value: {np.min(data):.6f}")
                    print(f"        Max value: {np.max(data):.6f}")
                    print(f"        Mean: {np.mean(data):.6f}")
                    print(f"        Std Dev: {np.std(data):.6f}")
                elif np.issubdtype(data.dtype, np.datetime64):
                    # DateTime data
                    print(f"        Min time: {np.min(data)}")
                    print(f"        Max time: {np.max(data)}")
                else:
                    # String or other data
                    print(f"        Sample values: {data[:3] if len(data) > 3 else data}")
                
                print(f"        First 5 values: {data[:5]}")
                if len(data) > 5:
                    print(f"        Last 5 values: {data[-5:]}")
            else:
                print(f"      Data Info: No data or empty")
    
    print("\n" + "=" * 80)
    
    # Summary
    total_groups = len(list(tdms_file.groups()))
    total_channels = sum(len(list(group.channels())) for group in tdms_file.groups())
    
    print(f"📋 SUMMARY:")
    print(f"   Total groups: {total_groups}")
    print(f"   Total channels: {total_channels}")
    
    # List all channel names for easy reference
    print(f"\n📝 ALL CHANNEL NAMES:")
    for group in tdms_file.groups():
        for channel in group.channels():
            print(f"   {group.name} → {channel.name}")

if __name__ == "__main__":
    # Inspect your TDMS file
    tdms_path = "data/FRIGIDAIRE-2025-02-19-19-55-25.tdms"
    inspect_tdms_file(tdms_path)
