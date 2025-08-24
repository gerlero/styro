#!/usr/bin/env python3
"""
Simple test runner for mock package tests without pytest.
"""
import asyncio
import sys
import tempfile
import traceback
import unittest.mock
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

# Add current directory to path so we can import styro
sys.path.insert(0, str(Path(__file__).parent))

import typer
from styro._packages import Package


class MockPackage(Package):
    """Mock package for testing without external dependencies."""
    
    def __init__(self, name: str):
        super().__init__(name)
        self._test_metadata = {}
        self._test_installed = False
        self._test_sha = "mock_sha_123"
        self._test_upgrade_available = False
        
    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Set metadata for testing."""
        self._test_metadata = metadata
        
    def set_installed_state(self, installed: bool, sha: Optional[str] = None) -> None:
        """Set installation state for testing."""
        self._test_installed = installed
        if sha:
            self._test_sha = sha
        
    async def fetch(self) -> None:
        """Mock fetch that sets metadata."""
        self._metadata = self._test_metadata.copy()
        self._upgrade_available = self._test_upgrade_available
        
    async def download(self) -> Optional[str]:
        """Mock download that returns a SHA."""
        return self._test_sha
        
    def is_installed(self) -> bool:
        """Mock installation status."""
        return self._test_installed
        
    def installed_sha(self) -> Optional[str]:
        """Mock installed SHA."""
        return self._test_sha if self._test_installed else None
        
    def set_upgrade_available(self, available: bool) -> None:
        """Set whether an upgrade is available."""
        self._test_upgrade_available = available
        self._upgrade_available = available


def test_mock_package_creation():
    """Test creating mock packages."""
    print("Testing mock package creation...")
    pkg = MockPackage("test-package")
    assert pkg.name == "test-package"
    assert not pkg.is_installed()
    assert pkg.installed_sha() is None
    print("✓ Mock package creation test passed")


def test_mock_package_with_metadata():
    """Test mock package with metadata."""
    print("Testing mock package with metadata...")
    metadata = {"requires": ["dependency-1", "dependency-2"]}
    pkg = MockPackage("test-package")
    pkg.set_metadata(metadata)
    assert pkg._test_metadata == metadata
    print("✓ Mock package with metadata test passed")


def test_mock_package_installed():
    """Test mock package that is installed."""
    print("Testing installed mock package...")
    pkg = MockPackage("test-package")
    pkg.set_installed_state(True, "test_sha")
    assert pkg.is_installed()
    assert pkg.installed_sha() == "test_sha"
    print("✓ Installed mock package test passed")


async def test_mock_package_fetch():
    """Test mock package fetch operation."""
    print("Testing mock package fetch...")
    metadata = {"requires": ["dep1"]}
    pkg = MockPackage("test-package")
    pkg.set_metadata(metadata)
    
    await pkg.fetch()
    assert pkg._metadata == metadata
    print("✓ Mock package fetch test passed")


def test_mock_package_dependencies():
    """Test mock package dependency methods."""
    print("Testing mock package dependencies...")
    metadata = {"requires": ["dep1", "dep2"]}
    pkg = MockPackage("test-package")
    pkg.set_metadata(metadata)
    pkg._metadata = metadata
    
    deps = pkg.requested_dependencies()
    dep_names = {dep.name for dep in deps}
    assert dep_names == {"dep1", "dep2"}
    print("✓ Mock package dependencies test passed")


async def test_cycle_detection_no_cycle():
    """Test cycle detection with no cycle."""
    print("Testing cycle detection - no cycle...")
    
    # A -> B -> C (no cycle)
    pkg_a = MockPackage("package-a")
    pkg_b = MockPackage("package-b") 
    pkg_c = MockPackage("package-c")
    
    pkg_a.set_metadata({"requires": ["package-b"]})
    pkg_b.set_metadata({"requires": ["package-c"]})
    pkg_c.set_metadata({})
    
    # Set up metadata
    await pkg_a.fetch()
    await pkg_b.fetch()
    await pkg_c.fetch()
    
    # Mock the dependency relationships
    with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}), \
         patch.object(pkg_b, 'requested_dependencies', return_value={pkg_c}), \
         patch.object(pkg_c, 'requested_dependencies', return_value=set()), \
         patch.object(pkg_a, 'installed_dependents', return_value=set()), \
         patch.object(pkg_b, 'installed_dependents', return_value=set()), \
         patch.object(pkg_c, 'installed_dependents', return_value=set()):
        
        # Should not raise an exception
        try:
            await Package._detect_cycles({pkg_a})
            print("✓ Cycle detection (no cycle) test passed")
        except Exception as e:
            print(f"✗ Cycle detection (no cycle) test failed: {e}")
            raise


async def test_cycle_detection_with_cycle():
    """Test cycle detection with actual cycle."""
    print("Testing cycle detection - with cycle...")
    
    # A -> B -> A (cycle)
    pkg_a = MockPackage("package-a")
    pkg_b = MockPackage("package-b")
    
    pkg_a.set_metadata({"requires": ["package-b"]})
    pkg_b.set_metadata({"requires": ["package-a"]})
    
    # Set up metadata
    await pkg_a.fetch()
    await pkg_b.fetch()
    
    # Mock the dependency relationships
    with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}), \
         patch.object(pkg_b, 'requested_dependencies', return_value={pkg_a}), \
         patch.object(pkg_a, 'installed_dependents', return_value=set()), \
         patch.object(pkg_b, 'installed_dependents', return_value=set()):
        
        # Should raise typer.Exit due to cycle
        try:
            await Package._detect_cycles({pkg_a})
            print("✗ Cycle detection (with cycle) test failed - should have raised exception")
            assert False, "Expected typer.Exit exception"
        except typer.Exit as e:
            if e.exit_code == 1:
                print("✓ Cycle detection (with cycle) test passed")
            else:
                print(f"✗ Cycle detection (with cycle) test failed - wrong exit code: {e.exit_code}")
                raise
        except Exception as e:
            print(f"✗ Cycle detection (with cycle) test failed - unexpected exception: {e}")
            raise


async def test_resolve_simple_package():
    """Test resolving a simple package without dependencies."""
    print("Testing simple package resolution...")
    pkg = MockPackage("simple-package")
    await pkg.fetch()
    
    resolved = await pkg.resolve()
    assert pkg in resolved
    print("✓ Simple package resolution test passed")


async def test_upgrade_scenario():
    """Test package upgrade scenario."""
    print("Testing upgrade scenario...")
    # Package is already installed but upgrade is available
    pkg = MockPackage("upgrade-package")
    pkg.set_installed_state(True, "old_sha")
    pkg.set_upgrade_available(True)
    
    await pkg.fetch()
    resolved = await pkg.resolve(upgrade=True)
    
    # Should include the package for upgrade
    assert pkg in resolved
    print("✓ Upgrade scenario test passed")


async def test_force_reinstall_scenario():
    """Test force reinstall scenario."""
    print("Testing force reinstall scenario...")
    # Package is installed and up-to-date, but force reinstall requested
    pkg = MockPackage("reinstall-package")
    pkg.set_installed_state(True, "current_sha")
    pkg.set_upgrade_available(False)  # No upgrade available
    
    await pkg.fetch()
    resolved = await pkg.resolve(_force_reinstall=True)
    
    # Should include the package for reinstall
    assert pkg in resolved
    print("✓ Force reinstall scenario test passed")


async def run_async_tests():
    """Run all async tests."""
    # Mock OpenFOAM platform_path for async tests too
    mock_platform_path = Path(tempfile.gettempdir()) / "mock_openfoam"
    mock_platform_path.mkdir(exist_ok=True)
    
    with patch('styro._packages.platform_path', return_value=mock_platform_path), \
         patch('styro._openfoam.platform_path', return_value=mock_platform_path):
        
        try:
            await test_mock_package_fetch()
            await test_cycle_detection_no_cycle()
            await test_cycle_detection_with_cycle()
            await test_resolve_simple_package()
            await test_upgrade_scenario()
            await test_force_reinstall_scenario()
            return True
        except Exception as e:
            print(f"Async test failed: {e}")
            traceback.print_exc()
            return False


def main():
    """Run all tests."""
    print("Running mock package tests...")
    print("=" * 50)
    
    failed = False
    
    # Mock OpenFOAM platform_path to avoid environment dependency
    mock_platform_path = Path(tempfile.gettempdir()) / "mock_openfoam"
    mock_platform_path.mkdir(exist_ok=True)
    
    with patch('styro._packages.platform_path', return_value=mock_platform_path), \
         patch('styro._openfoam.platform_path', return_value=mock_platform_path):
        
        # Run sync tests
        try:
            test_mock_package_creation()
            test_mock_package_with_metadata()
            test_mock_package_installed()
            test_mock_package_dependencies()
        except Exception as e:
            print(f"Sync test failed: {e}")
            traceback.print_exc()
            failed = True
        
        # Run async tests
        success = asyncio.run(run_async_tests())
        if not success:
            failed = True
    
    print("=" * 50)
    if failed:
        print("❌ Some tests failed")
        return 1
    else:
        print("✅ All tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())