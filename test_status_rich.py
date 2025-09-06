#!/usr/bin/env python3
"""Test the Rich-based Status implementation."""

import asyncio
import time
import sys
from pathlib import Path

# Add the styro package to path
sys.path.insert(0, str(Path(__file__).parent))

from styro._status import Status


def test_basic_status():
    """Test basic Status functionality without event loop."""
    print("Testing basic Status functionality...")
    
    with Status("Basic test") as status:
        time.sleep(0.5)
        status("Working on something")
        time.sleep(0.5)
        print("This should interrupt cleanly")
        time.sleep(0.5)
    
    print("Basic test completed")


async def test_async_status():
    """Test Status functionality with async event loop."""
    print("\nTesting async Status functionality...")
    
    with Status("Async test") as status:
        await asyncio.sleep(0.5)
        status("Async working")
        await asyncio.sleep(0.5)
        print("This should interrupt cleanly in async")
        await asyncio.sleep(0.5)
    
    print("Async test completed")


async def test_nested_status():
    """Test nested Status functionality."""
    print("\nTesting nested Status functionality...")
    
    with Status("Outer task") as outer:
        await asyncio.sleep(0.3)
        outer("Outer working")
        await asyncio.sleep(0.3)
        
        with Status("Inner task") as inner:
            await asyncio.sleep(0.3)
            inner("Inner working")
            await asyncio.sleep(0.3)
            print("Interrupting nested status")
            await asyncio.sleep(0.3)
        
        outer("Back to outer")
        await asyncio.sleep(0.3)
    
    print("Nested test completed")


if __name__ == "__main__":
    # Test without event loop
    test_basic_status()
    
    # Test with event loop
    asyncio.run(test_async_status())
    asyncio.run(test_nested_status())
    
    print("\nAll tests completed successfully!")