"""
CLI Integration tests with mock packages to validate end-to-end functionality.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import typer
from typer.testing import CliRunner

from styro.__main__ import app
from styro._packages import Package


def get_test_platform_path():
    """Get a test platform path."""
    test_path = Path(tempfile.gettempdir()) / "styro_cli_test"
    test_path.mkdir(exist_ok=True)
    return test_path


def setup_mock_environment():
    """Set up a clean mock OpenFOAM environment for testing."""
    test_path = get_test_platform_path()
    
    # Clean up and recreate directory structure
    import shutil
    if test_path.exists():
        shutil.rmtree(test_path)
    test_path.mkdir(parents=True, exist_ok=True)
    
    (test_path / "styro").mkdir(exist_ok=True)
    (test_path / "bin").mkdir(exist_ok=True)
    (test_path / "lib").mkdir(exist_ok=True)
    
    # Create fresh installed.json with correct version
    installed_file = test_path / "styro" / "installed.json"
    with installed_file.open("w") as f:
        json.dump({"version": 1, "packages": {}}, f)
    
    return test_path


class MockCLIPackage(Package):
    """Mock package that integrates with CLI operations."""
    
    _instances = {}  # Class variable to track instances
    
    def __init__(self, name: str):
        super().__init__(name)
        self._test_metadata = {}
        self._test_apps = []
        self._test_libs = []
        MockCLIPackage._instances[name] = self
        
    @classmethod
    def get_instance(cls, name: str):
        """Get existing instance or create new one."""
        if name not in cls._instances:
            cls._instances[name] = cls(name)
        return cls._instances[name]
        
    @classmethod 
    def clear_instances(cls):
        """Clear all instances."""
        cls._instances.clear()
        
    def configure(self, metadata: Dict[str, Any] = None, apps: list = None, libs: list = None):
        """Configure the mock package."""
        self._test_metadata = metadata or {}
        self._test_apps = apps or []
        self._test_libs = libs or []
        return self
        
    async def fetch(self) -> None:
        """Mock fetch operation."""
        self._metadata = self._test_metadata.copy()
        
    async def download(self) -> str:
        """Mock download operation."""
        return f"mock_sha_{self.name}"
        
    def is_installed(self) -> bool:
        """Check if package is installed by reading mock installed.json."""
        test_path = get_test_platform_path()
        installed_file = test_path / "styro" / "installed.json"
        
        try:
            with installed_file.open("r") as f:
                installed = json.load(f)
            return self.name in installed.get("packages", {})
        except (FileNotFoundError, json.JSONDecodeError):
            return False
            
    def installed_sha(self) -> str:
        """Get installed SHA from mock installed.json."""
        if not self.is_installed():
            return None
            
        test_path = get_test_platform_path()
        installed_file = test_path / "styro" / "installed.json"
        
        try:
            with installed_file.open("r") as f:
                installed = json.load(f)
            return installed["packages"][self.name].get("sha")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None
    
    async def install(self, *, upgrade: bool = False, _force_reinstall: bool = False, _deps=True) -> None:
        """Mock install operation that updates installed.json."""
        test_path = get_test_platform_path()
        installed_file = test_path / "styro" / "installed.json"
        
        try:
            with installed_file.open("r") as f:
                installed = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            installed = {"version": 1, "packages": {}}
            
        # Add package to installed packages
        installed["packages"][self.name] = {
            "sha": f"mock_sha_{self.name}",
            "origin": f"mock://repo/{self.name}",
            "requires": self._test_metadata.get("requires", []),
            "apps": self._test_apps,
            "libs": self._test_libs
        }
        
        with installed_file.open("w") as f:
            json.dump(installed, f, indent=2)
            
        print(f"✅ Installed {self.name}")
        
    async def uninstall(self, *, _force: bool = False, _keep_pkg: bool = False) -> None:
        """Mock uninstall operation that updates installed.json."""
        test_path = get_test_platform_path()
        installed_file = test_path / "styro" / "installed.json"
        
        try:
            with installed_file.open("r") as f:
                installed = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            installed = {"version": 1, "packages": {}}
            
        # Remove package from installed packages
        if self.name in installed.get("packages", {}):
            del installed["packages"][self.name]
            
        with installed_file.open("w") as f:
            json.dump(installed, f, indent=2)
            
        print(f"✅ Uninstalled {self.name}")


def mock_package_factory(package_spec: str):
    """Factory function to create mock packages based on package specification."""
    # Parse package specification
    if "@" in package_spec:
        name, origin = package_spec.split("@", 1)
        name = name.strip().lower().replace("_", "-")
    else:
        name = package_spec.lower().replace("_", "-")
        origin = f"mock://repo/{name}"
    
    # Return existing instance or create new one
    return MockCLIPackage.get_instance(name)


def test_cli_basic_commands():
    """Test basic CLI commands work with mocking."""
    print("Testing basic CLI commands...")
    runner = CliRunner()
    
    with patch('styro._packages.platform_path', return_value=get_test_platform_path()), \
         patch('styro._self.check_for_new_version', return_value=False):
        
        # Test version command
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "styro" in result.stdout
        print("✓ Version command test passed")
        
        # Test help command
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "install" in result.stdout
        print("✓ Help command test passed")


def test_cli_mock_package_operations():
    """Test CLI package operations with mock packages."""
    print("Testing CLI package operations...")
    runner = CliRunner()
    
    # Clear any existing instances
    MockCLIPackage.clear_instances()
    
    # Set up test environment
    test_path = setup_mock_environment()
    
    # Configure mock packages
    mock_pkg_a = MockCLIPackage.get_instance("test-package-a").configure(
        metadata={"requires": ["test-package-b"]},
        apps=["app1"],
        libs=["lib1"]
    )
    mock_pkg_b = MockCLIPackage.get_instance("test-package-b").configure(
        metadata={},
        apps=["app2"],
        libs=["lib2"]
    )
    
    with patch('styro._packages.platform_path', return_value=test_path), \
         patch('styro._packages.Package.__new__', side_effect=mock_package_factory), \
         patch('styro._self.check_for_new_version', return_value=False):
        
        # Test that packages start as not installed
        assert not mock_pkg_a.is_installed()
        assert not mock_pkg_b.is_installed()
        print("✓ Initial state: packages not installed")
        
        # Simulate installation (we can't easily test real CLI install without OpenFOAM)
        # So we'll test the mock installation directly
        async def test_install():
            await mock_pkg_b.install()
            await mock_pkg_a.install()
            
        asyncio.run(test_install())
        
        assert mock_pkg_a.is_installed()
        assert mock_pkg_b.is_installed()
        print("✓ Mock installation test passed")
        
        # Test uninstallation
        async def test_uninstall():
            await mock_pkg_a.uninstall()
            
        asyncio.run(test_uninstall())
        
        assert not mock_pkg_a.is_installed()
        assert mock_pkg_b.is_installed()  # B should still be installed
        print("✓ Mock uninstallation test passed")


def test_dependency_scenarios_with_cycles():
    """Test dependency scenarios including cycle detection."""
    print("Testing dependency scenarios...")
    
    # Clear instances
    MockCLIPackage.clear_instances()
    test_path = setup_mock_environment()
    
    # Create packages with circular dependency
    mock_pkg_a = MockCLIPackage.get_instance("cycle-a").configure(
        metadata={"requires": ["cycle-b"]}
    )
    mock_pkg_b = MockCLIPackage.get_instance("cycle-b").configure(
        metadata={"requires": ["cycle-a"]}
    )
    
    with patch('styro._packages.platform_path', return_value=test_path):
        async def test_cycle_detection():
            await mock_pkg_a.fetch()
            await mock_pkg_b.fetch()
            
            # Mock the dependency relationships for cycle detection
            with patch.object(mock_pkg_a, 'requested_dependencies', return_value={mock_pkg_b}), \
                 patch.object(mock_pkg_b, 'requested_dependencies', return_value={mock_pkg_a}), \
                 patch.object(mock_pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(mock_pkg_b, 'installed_dependents', return_value=set()):
                
                try:
                    await Package._detect_cycles({mock_pkg_a})
                    assert False, "Should have detected cycle"
                except typer.Exit as e:
                    assert e.exit_code == 1
                    
        asyncio.run(test_cycle_detection())
        print("✓ Cycle detection test passed")


def test_upgrade_and_reinstall_scenarios():
    """Test upgrade and reinstall scenarios."""
    print("Testing upgrade and reinstall scenarios...")
    
    MockCLIPackage.clear_instances()
    test_path = setup_mock_environment()
    
    # Create a package that can be upgraded
    mock_pkg = MockCLIPackage.get_instance("upgrade-test").configure(
        metadata={},
        apps=["app1"],
        libs=["lib1"]
    )
    
    with patch('styro._packages.platform_path', return_value=test_path):
        async def test_upgrade_scenario():
            # Install the package first
            await mock_pkg.install()
            assert mock_pkg.is_installed()
            
            # Test that resolve with upgrade=False doesn't include already installed package
            resolved = await mock_pkg.resolve(upgrade=False)
            assert len(resolved) == 0  # Should be empty for installed package without upgrade
            
            # Test that resolve with _force_reinstall=True includes the package
            resolved = await mock_pkg.resolve(_force_reinstall=True)
            assert mock_pkg in resolved
            
            # Test uninstall
            await mock_pkg.uninstall()
            assert not mock_pkg.is_installed()
            
        asyncio.run(test_upgrade_scenario())
        print("✓ Upgrade/reinstall scenario test passed")


def test_complex_dependency_resolution():
    """Test complex dependency resolution scenarios."""
    print("Testing complex dependency resolution...")
    
    MockCLIPackage.clear_instances()
    test_path = setup_mock_environment()
    
    # Create diamond dependency: A -> B,C; B -> D; C -> D
    mock_pkg_a = MockCLIPackage.get_instance("diamond-a").configure(
        metadata={"requires": ["diamond-b", "diamond-c"]}
    )
    mock_pkg_b = MockCLIPackage.get_instance("diamond-b").configure(
        metadata={"requires": ["diamond-d"]}
    )
    mock_pkg_c = MockCLIPackage.get_instance("diamond-c").configure(
        metadata={"requires": ["diamond-d"]}
    )
    mock_pkg_d = MockCLIPackage.get_instance("diamond-d").configure(
        metadata={}
    )
    
    with patch('styro._packages.platform_path', return_value=test_path):
        async def test_diamond_resolution():
            await mock_pkg_a.fetch()
            await mock_pkg_b.fetch()
            await mock_pkg_c.fetch()
            await mock_pkg_d.fetch()
            
            # Mock the dependency relationships
            with patch.object(mock_pkg_a, 'requested_dependencies', return_value={mock_pkg_b, mock_pkg_c}), \
                 patch.object(mock_pkg_b, 'requested_dependencies', return_value={mock_pkg_d}), \
                 patch.object(mock_pkg_c, 'requested_dependencies', return_value={mock_pkg_d}), \
                 patch.object(mock_pkg_d, 'requested_dependencies', return_value=set()), \
                 patch.object(mock_pkg_a, 'installed_dependents', return_value=set()), \
                 patch.object(mock_pkg_b, 'installed_dependents', return_value=set()), \
                 patch.object(mock_pkg_c, 'installed_dependents', return_value=set()), \
                 patch.object(mock_pkg_d, 'installed_dependents', return_value=set()):
                
                # Should not detect cycles in diamond pattern
                await Package._detect_cycles({mock_pkg_a})
                
                # Test resolution with mocked dependencies
                with patch.object(mock_pkg_b, 'resolve', return_value={mock_pkg_b, mock_pkg_d}), \
                     patch.object(mock_pkg_c, 'resolve', return_value={mock_pkg_c, mock_pkg_d}), \
                     patch.object(mock_pkg_d, 'resolve', return_value={mock_pkg_d}):
                    
                    resolved = await mock_pkg_a.resolve()
                    assert mock_pkg_a in resolved
                    
        asyncio.run(test_diamond_resolution())
        print("✓ Complex dependency resolution test passed")


def main():
    """Run all CLI integration tests."""
    print("Running CLI Integration Tests with Mock Packages")
    print("=" * 60)
    
    try:
        test_cli_basic_commands()
        test_cli_mock_package_operations()
        test_dependency_scenarios_with_cycles()
        test_upgrade_and_reinstall_scenarios()
        test_complex_dependency_resolution()
        
        print("=" * 60)
        print("✅ All CLI integration tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ CLI integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)