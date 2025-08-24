"""
Tests for styro package manager using mock packages.

These tests use mock packages to verify basic functionality and edge cases
without requiring external dependencies or OpenFOAM.
"""
import asyncio
import json
import tempfile
import unittest.mock
from pathlib import Path
from typing import Any, Dict, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import typer
from typer.testing import CliRunner

from styro import __version__
from styro.__main__ import app
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


def get_mock_platform_path():
    """Get a mock platform path for testing."""
    mock_path = Path(tempfile.gettempdir()) / "mock_styro_test"
    mock_path.mkdir(exist_ok=True)
    return mock_path


class TestMockPackages:
    """Test basic functionality with mock packages."""
    
    def test_mock_package_creation(self):
        """Test creating mock packages."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            pkg = MockPackage("test-package")
            assert pkg.name == "test-package"
            assert not pkg.is_installed()
            assert pkg.installed_sha() is None
        
    def test_mock_package_with_metadata(self):
        """Test mock package with metadata."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            metadata = {"requires": ["dependency-1", "dependency-2"]}
            pkg = MockPackage("test-package")
            pkg.set_metadata(metadata)
            assert pkg._test_metadata == metadata
        
    def test_mock_package_installed(self):
        """Test mock package that is installed."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            pkg = MockPackage("test-package")
            pkg.set_installed_state(True, "test_sha")
            assert pkg.is_installed()
            assert pkg.installed_sha() == "test_sha"
        
    @pytest.mark.asyncio
    async def test_mock_package_fetch(self):
        """Test mock package fetch operation."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            metadata = {"requires": ["dep1"]}
            pkg = MockPackage("test-package")
            pkg.set_metadata(metadata)
            
            await pkg.fetch()
            assert pkg._metadata == metadata
        
    def test_mock_package_dependencies(self):
        """Test mock package dependency methods."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Create mock package with dependencies
            metadata = {"requires": ["dep1", "dep2"]}
            pkg = MockPackage("test-package")
            pkg.set_metadata(metadata)
            pkg._metadata = metadata
            
            deps = pkg.requested_dependencies()
            dep_names = {dep.name for dep in deps}
            assert dep_names == {"dep1", "dep2"}


class TestDependencyResolution:
    """Test dependency resolution with mock packages."""
    
    @pytest.mark.asyncio
    async def test_resolve_simple_package(self):
        """Test resolving a simple package without dependencies."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            pkg = MockPackage("simple-package")
            await pkg.fetch()
            
            resolved = await pkg.resolve()
            assert pkg in resolved
        
    @pytest.mark.asyncio
    async def test_resolve_with_dependencies(self):
        """Test resolving a package with dependencies."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Create main package with dependencies
            main_pkg = MockPackage("main-package")
            main_pkg.set_metadata({"requires": ["dep1", "dep2"]})
            
            # Mock the dependency resolution by patching requested_dependencies
            with patch.object(main_pkg, 'requested_dependencies') as mock_deps:
                dep1 = MockPackage("dep1")
                dep2 = MockPackage("dep2")
                mock_deps.return_value = {dep1, dep2}
                
                # Mock the resolve calls for dependencies
                with patch.object(dep1, 'resolve', return_value={dep1}) as mock_dep1_resolve, \
                     patch.object(dep2, 'resolve', return_value={dep2}) as mock_dep2_resolve:
                    
                    await main_pkg.fetch()
                    resolved = await main_pkg.resolve()
                    
                    # Should include main package and its dependencies
                    assert main_pkg in resolved
                    assert dep1 in resolved
                    assert dep2 in resolved
                    
                    # Verify dependency resolve was called with upgrade=True
                    mock_dep1_resolve.assert_called_once()
                    mock_dep2_resolve.assert_called_once()


class TestCycleDetection:
    """Test dependency cycle detection with mock packages."""
    
    @pytest.mark.asyncio
    async def test_no_cycle_simple_chain(self):
        """Test cycle detection with simple dependency chain (no cycle)."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
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
                await Package._detect_cycles({pkg_a})
                
    @pytest.mark.asyncio
    async def test_cycle_detection_simple_cycle(self):
        """Test cycle detection with simple circular dependency."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
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
                with pytest.raises(typer.Exit) as exc_info:
                    await Package._detect_cycles({pkg_a})
                assert exc_info.value.exit_code == 1
                
    @pytest.mark.asyncio 
    async def test_cycle_detection_longer_cycle(self):
        """Test cycle detection with longer circular dependency."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # A -> B -> C -> A (cycle)
            pkg_a = MockPackage("package-a")
            pkg_b = MockPackage("package-b")
            pkg_c = MockPackage("package-c")
            
            pkg_a.set_metadata({"requires": ["package-b"]})
            pkg_b.set_metadata({"requires": ["package-c"]})
            pkg_c.set_metadata({"requires": ["package-a"]})
            
            # Set up metadata
            await pkg_a.fetch()
            await pkg_b.fetch()
            await pkg_c.fetch()
            
            # Mock the dependency relationships
            with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}), \
                 patch.object(pkg_b, 'requested_dependencies', return_value={pkg_c}), \
                 patch.object(pkg_c, 'requested_dependencies', return_value={pkg_a}), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_b, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_c, 'installed_dependents', return_value=set()):
                
                # Should raise typer.Exit due to cycle
                with pytest.raises(typer.Exit) as exc_info:
                    await Package._detect_cycles({pkg_a})
                assert exc_info.value.exit_code == 1
    
    @pytest.mark.asyncio
    async def test_cycle_detection_self_dependency(self):
        """Test cycle detection with self-dependency."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # A -> A (self-cycle)
            pkg_a = MockPackage("package-a")
            pkg_a.set_metadata({"requires": ["package-a"]})
            
            await pkg_a.fetch()
            
            # Mock the dependency relationships  
            with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_a}), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()):
                
                # Should raise typer.Exit due to self-cycle
                with pytest.raises(typer.Exit) as exc_info:
                    await Package._detect_cycles({pkg_a})
                assert exc_info.value.exit_code == 1


class TestEdgeCases:
    """Test edge cases involving reinstalling and updating packages."""
    
    @pytest.mark.asyncio
    async def test_upgrade_scenario(self):
        """Test package upgrade scenario."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Package is already installed but upgrade is available
            pkg = MockPackage("upgrade-package")
            pkg.set_installed_state(True, "old_sha")
            pkg.set_upgrade_available(True)
            
            await pkg.fetch()
            resolved = await pkg.resolve(upgrade=True)
            
            # Should include the package for upgrade
            assert pkg in resolved
        
    @pytest.mark.asyncio
    async def test_force_reinstall_scenario(self):
        """Test force reinstall scenario."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Package is installed and up-to-date, but force reinstall requested
            pkg = MockPackage("reinstall-package")
            pkg.set_installed_state(True, "current_sha")
            pkg.set_upgrade_available(False)  # No upgrade available
            
            await pkg.fetch()
            resolved = await pkg.resolve(_force_reinstall=True)
            
            # Should include the package for reinstall
            assert pkg in resolved
        
    @pytest.mark.asyncio
    async def test_installed_dependents_force_reinstall(self):
        """Test that installed dependents are force reinstalled."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Package A depends on Package B, and A is installed
            pkg_b = MockPackage("package-b")
            pkg_a = MockPackage("package-a")
            
            pkg_b.set_installed_state(True)
            pkg_a.set_installed_state(True)
            pkg_a.set_metadata({"requires": ["package-b"]})
            
            await pkg_b.fetch()
            await pkg_a.fetch()
            
            # Mock that A depends on B (installed dependent)
            with patch.object(pkg_b, 'installed_dependents', return_value={pkg_a}), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_b, 'requested_dependencies', return_value=set()), \
                 patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}):
                
                # Mock resolve for pkg_a to return itself when force_reinstall=True
                with patch.object(pkg_a, 'resolve') as mock_resolve:
                    mock_resolve.return_value = {pkg_a}
                    
                    resolved = await pkg_b.resolve()
                    
                    # pkg_a should be called with force_reinstall=True
                    mock_resolve.assert_called_once()
                    call_args = mock_resolve.call_args
                    assert call_args.kwargs.get('_force_reinstall') is True
                    
    @pytest.mark.asyncio
    async def test_cycle_with_upgrade_logic(self):
        """Test cycle detection considers upgrade/force_reinstall logic."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Create packages where cycle is only traversed under upgrade conditions
            pkg_a = MockPackage("package-a")
            pkg_b = MockPackage("package-b")
            
            pkg_a.set_installed_state(True)
            pkg_b.set_installed_state(True)
            pkg_a.set_metadata({"requires": ["package-b"]})
            pkg_b.set_metadata({"requires": ["package-a"]})
            
            await pkg_a.fetch()
            await pkg_b.fetch()
            
            # Mock dependencies and installed status
            with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}), \
                 patch.object(pkg_b, 'requested_dependencies', return_value={pkg_a}), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_b, 'installed_dependents', return_value=set()):
                
                # With upgrade=False, already installed packages should not cause cycle
                # (because they exit early in the cycle detection logic)
                # This tests the early return logic in _detect_cycles
                try:
                    await Package._detect_cycles({pkg_a}, upgrade=False)
                    # Should not raise if packages are already installed and no upgrade
                except typer.Exit:
                    pytest.fail("Cycle detection should not fail for installed packages without upgrade")
                    
                # With upgrade=True, should detect the cycle
                with pytest.raises(typer.Exit) as exc_info:
                    await Package._detect_cycles({pkg_a}, upgrade=True)
                assert exc_info.value.exit_code == 1

    @pytest.mark.asyncio
    async def test_complex_dependency_tree_no_cycle(self):
        """Test complex dependency tree without cycles."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Create a diamond dependency pattern: A -> B,C; B -> D; C -> D (no cycle)
            pkg_a = MockPackage("package-a")
            pkg_b = MockPackage("package-b")
            pkg_c = MockPackage("package-c") 
            pkg_d = MockPackage("package-d")
            
            pkg_a.set_metadata({"requires": ["package-b", "package-c"]})
            pkg_b.set_metadata({"requires": ["package-d"]})
            pkg_c.set_metadata({"requires": ["package-d"]})
            pkg_d.set_metadata({})
            
            await pkg_a.fetch()
            await pkg_b.fetch()
            await pkg_c.fetch()
            await pkg_d.fetch()
            
            # Mock the dependency relationships
            with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b, pkg_c}), \
                 patch.object(pkg_b, 'requested_dependencies', return_value={pkg_d}), \
                 patch.object(pkg_c, 'requested_dependencies', return_value={pkg_d}), \
                 patch.object(pkg_d, 'requested_dependencies', return_value=set()), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_b, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_c, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_d, 'installed_dependents', return_value=set()):
                
                # Should not raise an exception
                await Package._detect_cycles({pkg_a})


# Simple test runner for when pytest is not available



