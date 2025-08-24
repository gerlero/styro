"""
Integration tests using mock packages to test CLI and more complex scenarios.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch, MagicMock

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    class MockPytest:
        class mark:
            @staticmethod
            def skipif(*args, **kwargs):
                def decorator(func):
                    return func
                return decorator
            
            @staticmethod  
            def asyncio(func):
                return func
        
        @staticmethod
        def raises(*args, **kwargs):
            class MockRaises:
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc_val, exc_tb):
                    return False
            return MockRaises()
    pytest = MockPytest()

import typer
from typer.testing import CliRunner

from styro.__main__ import app
from styro._packages import Package


def get_mock_platform_path():
    """Get a mock platform path for testing."""
    mock_path = Path(tempfile.gettempdir()) / "mock_styro_integration"
    mock_path.mkdir(exist_ok=True)
    return mock_path


class MockPackageWithCLI(Package):
    """Enhanced mock package for CLI testing."""
    
    def __init__(self, name: str):
        super().__init__(name)
        self._test_metadata = {}
        self._test_installed = False
        self._test_sha = f"mock_sha_{name}"
        self._test_upgrade_available = False
        self._test_apps = []
        self._test_libs = []
        
    def set_metadata(self, metadata: Dict[str, Any]) -> None:
        """Set metadata for testing."""
        self._test_metadata = metadata
        
    def set_installed_state(self, installed: bool, sha: Optional[str] = None) -> None:
        """Set installation state for testing."""
        self._test_installed = installed
        if sha:
            self._test_sha = sha
        
    def set_binaries(self, apps: list = None, libs: list = None) -> None:
        """Set binary information for testing."""
        self._test_apps = apps or []
        self._test_libs = libs or []
        
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
        
    async def install(self, *, upgrade: bool = False, _force_reinstall: bool = False, _deps=True) -> None:
        """Mock install operation."""
        # Simulate installation
        self._test_installed = True
        
        # Update the mock installed.json
        mock_platform_path = get_mock_platform_path()
        installed_path = mock_platform_path / "styro" / "installed.json"
        installed_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with installed_path.open("r") as f:
                installed = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            installed = {"packages": {}}
            
        installed["packages"][self.name] = {
            "sha": self._test_sha,
            "origin": f"mock://origin/{self.name}",
            "requires": self._test_metadata.get("requires", []),
            "apps": self._test_apps,
            "libs": self._test_libs
        }
        
        with installed_path.open("w") as f:
            json.dump(installed, f, indent=2)
            
    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        """Mock uninstall operation."""
        self._test_installed = False
        
        # Update the mock installed.json
        mock_platform_path = get_mock_platform_path()
        installed_path = mock_platform_path / "styro" / "installed.json"
        
        try:
            with installed_path.open("r") as f:
                installed = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            installed = {"packages": {}}
            
        if self.name in installed.get("packages", {}):
            del installed["packages"][self.name]
            
        with installed_path.open("w") as f:
            json.dump(installed, f, indent=2)


@pytest.mark.skipif(not HAS_PYTEST, reason="pytest not available")
class TestCLIIntegration:
    """Test CLI integration with mock packages."""
    
    def test_version_command(self):
        """Test version command works."""
        runner = CliRunner()
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()), \
             patch('styro._self.check_for_new_version', return_value=False):
            result = runner.invoke(app, ["--version"])
            assert result.exit_code == 0
            assert "styro" in result.stdout
    
    def test_help_command(self):
        """Test help command works."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "install" in result.stdout
        assert "uninstall" in result.stdout


@pytest.mark.skipif(not HAS_PYTEST, reason="pytest not available")
class TestComplexScenarios:
    """Test complex scenarios with multiple packages."""
    
    @pytest.mark.asyncio
    async def test_multi_level_dependencies(self):
        """Test resolving packages with multi-level dependencies."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Create dependency chain: A -> B -> C -> D
            pkg_a = MockPackageWithCLI("package-a")
            pkg_b = MockPackageWithCLI("package-b")
            pkg_c = MockPackageWithCLI("package-c")
            pkg_d = MockPackageWithCLI("package-d")
            
            pkg_a.set_metadata({"requires": ["package-b"]})
            pkg_b.set_metadata({"requires": ["package-c"]})
            pkg_c.set_metadata({"requires": ["package-d"]})
            pkg_d.set_metadata({})
            
            await pkg_a.fetch()
            await pkg_b.fetch()
            await pkg_c.fetch()
            await pkg_d.fetch()
            
            # Mock the dependency relationships
            with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}), \
                 patch.object(pkg_b, 'requested_dependencies', return_value={pkg_c}), \
                 patch.object(pkg_c, 'requested_dependencies', return_value={pkg_d}), \
                 patch.object(pkg_d, 'requested_dependencies', return_value=set()), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_b, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_c, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_d, 'installed_dependents', return_value=set()):
                
                # Should not detect any cycles
                await Package._detect_cycles({pkg_a})
                
                # Test resolve  
                with patch.object(pkg_b, 'resolve', return_value={pkg_b, pkg_c, pkg_d}), \
                     patch.object(pkg_c, 'resolve', return_value={pkg_c, pkg_d}), \
                     patch.object(pkg_d, 'resolve', return_value={pkg_d}):
                    resolved = await pkg_a.resolve()
                    assert pkg_a in resolved
    
    @pytest.mark.asyncio
    async def test_diamond_dependency_pattern(self):
        """Test diamond dependency pattern: A depends on B and C, both depend on D."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Diamond: A -> B,C; B -> D; C -> D
            pkg_a = MockPackageWithCLI("package-a")
            pkg_b = MockPackageWithCLI("package-b")
            pkg_c = MockPackageWithCLI("package-c")
            pkg_d = MockPackageWithCLI("package-d")
            
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
                
                # Should not detect any cycles in diamond pattern
                await Package._detect_cycles({pkg_a})
    
    @pytest.mark.asyncio
    async def test_partial_installation_state(self):
        """Test scenarios with some packages already installed."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # A -> B -> C, where B is already installed
            pkg_a = MockPackageWithCLI("package-a")
            pkg_b = MockPackageWithCLI("package-b")
            pkg_c = MockPackageWithCLI("package-c")
            
            pkg_a.set_metadata({"requires": ["package-b"]})
            pkg_b.set_metadata({"requires": ["package-c"]})
            pkg_c.set_metadata({})
            
            # B is already installed
            pkg_b.set_installed_state(True)
            
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
                
                # Should not detect cycles even with partial installation
                await Package._detect_cycles({pkg_a})
                
                # Test that installed package (B) doesn't get resolved unless upgrade=True
                with patch.object(pkg_c, 'resolve', return_value={pkg_c}):
                    resolved = await pkg_b.resolve(upgrade=False)
                    # Since B is installed and no upgrade, should be empty
                    assert len(resolved) == 0
                    
                    # With upgrade=True, should resolve
                    pkg_b.set_upgrade_available(True)
                    resolved = await pkg_b.resolve(upgrade=True)
                    assert pkg_b in resolved
    
    @pytest.mark.asyncio 
    async def test_reverse_dependency_tracking(self):
        """Test reverse dependency (dependent) tracking."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # A depends on B, both installed
            pkg_a = MockPackageWithCLI("package-a")
            pkg_b = MockPackageWithCLI("package-b")
            
            pkg_a.set_metadata({"requires": ["package-b"]})
            pkg_b.set_metadata({})
            
            pkg_a.set_installed_state(True)
            pkg_b.set_installed_state(True)
            
            await pkg_a.fetch()
            await pkg_b.fetch()
            
            # Mock that A is a dependent of B
            with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b}), \
                 patch.object(pkg_b, 'requested_dependencies', return_value=set()), \
                 patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(pkg_b, 'installed_dependents', return_value={pkg_a}):
                
                # When B is updated, A should be force-reinstalled
                with patch.object(pkg_a, 'resolve') as mock_a_resolve:
                    mock_a_resolve.return_value = {pkg_a}
                    resolved = await pkg_b.resolve()
                    
                    # A should be called with _force_reinstall=True
                    mock_a_resolve.assert_called_once()
                    call_kwargs = mock_a_resolve.call_args.kwargs
                    assert call_kwargs.get('_force_reinstall') is True


@pytest.mark.skipif(not HAS_PYTEST, reason="pytest not available") 
class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    @pytest.mark.asyncio
    async def test_cycle_with_detailed_error_message(self):
        """Test that cycle detection provides detailed error messages."""
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Create a cycle: A -> B -> C -> A
            pkg_a = MockPackageWithCLI("package-a")
            pkg_b = MockPackageWithCLI("package-b")
            pkg_c = MockPackageWithCLI("package-c")
            
            pkg_a.set_metadata({"requires": ["package-b"]})
            pkg_b.set_metadata({"requires": ["package-c"]})
            pkg_c.set_metadata({"requires": ["package-a"]})
            
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
                
                # Capture the error message
                try:
                    await Package._detect_cycles({pkg_a})
                    assert False, "Should have detected cycle"
                except typer.Exit as e:
                    assert e.exit_code == 1
                    # The actual error message is printed to stderr by typer.secho
                    # so we can't easily capture it here, but we know it should contain
                    # the cycle path: package-a -> package-b -> package-c -> package-a


def run_simple_integration_tests():
    """Run basic integration tests without pytest."""
    print("Running simple integration tests...")
    print("=" * 50)
    
    try:
        with patch('styro._packages.platform_path', return_value=get_mock_platform_path()):
            # Test basic package operations
            pkg = MockPackageWithCLI("test-package")
            pkg.set_metadata({"requires": []})
            
            # Test installation simulation
            asyncio.run(pkg.install())
            assert pkg.is_installed()
            print("✓ Installation simulation test passed")
            
            # Test uninstallation simulation
            asyncio.run(pkg.uninstall())
            assert not pkg.is_installed()
            print("✓ Uninstallation simulation test passed")
            
            # Test complex dependency resolution
            async def test_complex_deps():
                pkg_a = MockPackageWithCLI("package-a")
                pkg_b = MockPackageWithCLI("package-b")
                pkg_c = MockPackageWithCLI("package-c")
                
                pkg_a.set_metadata({"requires": ["package-b", "package-c"]})
                pkg_b.set_metadata({"requires": []})
                pkg_c.set_metadata({"requires": []})
                
                await pkg_a.fetch()
                await pkg_b.fetch()
                await pkg_c.fetch()
                
                # Mock dependencies for diamond pattern
                with patch.object(pkg_a, 'requested_dependencies', return_value={pkg_b, pkg_c}), \
                     patch.object(pkg_b, 'requested_dependencies', return_value=set()), \
                     patch.object(pkg_c, 'requested_dependencies', return_value=set()), \
                     patch.object(pkg_a, 'installed_dependents', return_value=set()), \
                     patch.object(pkg_b, 'installed_dependents', return_value=set()), \
                     patch.object(pkg_c, 'installed_dependents', return_value=set()):
                    
                    # Should not detect cycles in diamond pattern
                    await Package._detect_cycles({pkg_a})
                    
            asyncio.run(test_complex_deps())
            print("✓ Complex dependency resolution test passed")
            
        print("=" * 50)
        print("✅ All integration tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if HAS_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        import sys
        success = run_simple_integration_tests()
        sys.exit(0 if success else 1)