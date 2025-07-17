#!/usr/bin/env python3
"""
TDMS Inspector - Streaming version for very large files
Uses npTDMS streaming capabilities to avoid memory issues
"""

import nptdms
import numpy as np
import sys
from pathlib import Path

def inspect_tdms_file_streaming(file_path):
    """Inspect TDMS file using streaming to avoid memory issues"""
    print(f"🔍 Inspecting TDMS file (streaming mode): {file_path}")
    print("=" * 80)
    
    try:
        # Check file size first
        file_size = Path(file_path).stat().st_size
        print(f"📄 FILE SIZE: {file_size / (1024*1024):.1f} MB")
        
        # Use open() method for streaming - only reads metadata initially
        with nptdms.TdmsFile.open(file_path) as tdms_file:
            print("✅ File opened successfully in streaming mode")
            
            # File-level properties
            print(f"\n📄 FILE PROPERTIES:")
            if hasattr(tdms_file, 'properties') and tdms_file.properties:
                for key, value in tdms_file.properties.items():
                    print(f"   {key}: {value}")
            else:
                print("   No file properties found")
            
            print("\n" + "=" * 80)
            
            # Get all groups and channels first (metadata only)
            all_groups = list(tdms_file.groups())
            print(f"📁 Found {len(all_groups)} groups")
            
            # Inspect each group structure
            total_channels = 0
            channel_info = []
            
            for group in all_groups:
                print(f"\n�� GROUP: {group.name}")
                print("-" * 40)
                
                # Group properties
                if hasattr(group, 'properties') and group.properties:
                    print("   Group Properties:")
                    for key, value in group.properties.items():
                        print(f"     {key}: {value}")
                
                # Get channels in this group
                group_channels = list(group.channels())
                print(f"   �� Channels in group: {len(group_channels)}")
                
                # Store channel info for later analysis
                for channel in group_channels:
                    channel_info.append({
                        'group': group.name,
                        'channel': channel.name,
                        'path': f"{group.name}/{channel.name}"
                    })
                    total_channels += 1
                    
                    print(f"     - {channel.name}")
                    
                    # Channel properties
                    if hasattr(channel, 'properties') and channel.properties:
                        print("       Properties:")
                        for key, value in channel.properties.items():
                            print(f"         {key}: {value}")
            
            print("\n" + "=" * 80)
            
            # Summary
            print(f"📋 SUMMARY:")
            print(f"   Total groups: {len(all_groups)}")
            print(f"   Total channels: {total_channels}")
            print(f"   File size: {file_size / (1024*1024):.1f} MB")
            
            # List all channel names
            print(f"\n📝 ALL CHANNEL NAMES:")
            for info in channel_info:
                print(f"   {info['group']} → {info['channel']}")
            
            # Now do streaming analysis of a few channels as example
            print(f"\n�� STREAMING ANALYSIS (sample channels):")
            print("=" * 80)
            
            # Pick first few channels for streaming analysis
            sample_channels = channel_info[:3]  # First 3 channels
            
            for i, info in enumerate(sample_channels):
                print(f"\n📊 Analyzing channel {i+1}/{len(sample_channels)}: {info['channel']}")
                
                try:
                    # Get the channel
                    channel = tdms_file[info['group']][info['channel']]
                    
                    # Use streaming to analyze data
                    channel_sum = 0.0
                    channel_length = 0
                    min_val = float('inf')
                    max_val = float('-inf')
                    sample_values = []
                    
                    # Stream through data chunks
                    chunk_count = 0
                    for chunk in channel.data_chunks():
                        chunk_data = chunk[:]
                        chunk_length = len(chunk_data)
                        
                        if chunk_length > 0:
                            channel_length += chunk_length
                            channel_sum += chunk_data.sum()
                            
                            # Track min/max
                            chunk_min = np.min(chunk_data)
                            chunk_max = np.max(chunk_data)
                            min_val = min(min_val, chunk_min)
                            max_val = max(max_val, chunk_max)
                            
                            # Collect sample values (first few from each chunk)
                            if len(sample_values) < 10:
                                sample_values.extend(chunk_data[:min(3, len(chunk_data))])
                        
                        chunk_count += 1
                        
                        # Limit analysis to avoid taking too long
                        if chunk_count > 10:  # Only analyze first 10 chunks
                            print(f"        ⚠️  Limiting analysis to first 10 chunks")
                            break
                    
                    if channel_length > 0:
                        mean_val = channel_sum / channel_length
                        print(f"        Sample count: {channel_length:,}")
                        print(f"        Min value: {min_val:.6f}")
                        print(f"        Max value: {max_val:.6f}")
                        print(f"        Mean: {mean_val:.6f}")
                        print(f"        Sample values: {sample_values[:5]}")
                        print(f"        Chunks analyzed: {chunk_count}")
                    else:
                        print(f"        No data found")
                        
                except Exception as e:
                    print(f"        Error analyzing channel: {e}")
            
            print(f"\n💡 RECOMMENDATIONS:")
            print(f"   - File has {total_channels} channels")
            print(f"   - Use streaming processing for full analysis")
            print(f"   - For processing, use: python -c \"from clients.cdaq.cdaq_client import CDAQClient; client = CDAQClient(); client.process_tdms_file('{file_path}')\"")
            
    except MemoryError:
        print("❌ Memory Error: File is too large even for streaming")
        print("�� Try using the cDAQ client for processing:")
        print(f"   python -c \"from clients.cdaq.cdaq_client import CDAQClient; client = CDAQClient(); client.process_tdms_file('{file_path}')\"")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error inspecting TDMS file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_tdms_streaming.py <tdms_file_path>")
        print("Example: python inspect_tdms_streaming.py data/FRIGIDAIRE-2025-02-19-19-55-25.tdms")
        sys.exit(1)
    
    tdms_path = sys.argv[1]
    
    try:
        inspect_tdms_file_streaming(tdms_path)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {tdms_path}")
        sys.exit(1) 