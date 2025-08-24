# Styro Mock Package Tests

This directory contains comprehensive tests for the styro package manager using mock packages that do not require external dependencies or OpenFOAM environment.

## Test Files

### Core Test Files

1. **`test_mock_packages.py`** - Basic mock package functionality
   - MockPackage class implementation
   - Basic package operations (creation, metadata, installation state)
   - Simple dependency resolution tests
   - Basic cycle detection tests

2. **`test_integration_mocks.py`** - Complex integration scenarios
   - Multi-level dependency chains
   - Diamond dependency patterns (shared dependencies)
   - Partial installation states
   - Reverse dependency tracking
   - Complex dependency resolution scenarios

3. **`test_cli_integration.py`** - End-to-end CLI integration
   - CLI command testing (version, help)
   - Package installation/uninstallation simulation
   - Dependency scenario testing
   - Upgrade and reinstall scenarios
   - Error handling validation

4. **`test_runner.py`** - Simple test runner for pytest-less environments
   - Self-contained test runner
   - Basic functionality verification
   - Async test support

## Test Categories

### Basic Functionality Tests
- ✅ Package creation and naming validation
- ✅ Metadata handling and configuration
- ✅ Installation state management
- ✅ Mock fetch/download operations
- ✅ Dependency relationship setup

### Edge Cases for Reinstalling/Updating
- ✅ Upgrade scenarios (packages with available updates)
- ✅ Force reinstall scenarios (up-to-date packages needing reinstallation)
- ✅ Partial installation states (mixed installed/uninstalled dependencies)
- ✅ Reverse dependency tracking (dependents forced to reinstall)
- ✅ Installation state transitions

### Dependency Cycle Detection Logic
- ✅ Simple circular dependencies (A → B → A)
- ✅ Longer circular chains (A → B → C → A)
- ✅ Self-dependencies (A → A)
- ✅ Complex dependency patterns (diamond dependencies)
- ✅ Cycle detection with upgrade logic conditions
- ✅ Early termination for installed packages

### CLI Integration
- ✅ Basic CLI commands functionality
- ✅ Package operations through CLI simulation
- ✅ Multi-level dependency resolution
- ✅ Error handling and validation
- ✅ Platform-independent operation

## Running the Tests

### Option 1: Individual Test Files
```bash
# Run basic mock package tests
python test_mock_packages.py

# Run integration tests
python test_integration_mocks.py

# Run CLI integration tests
python test_cli_integration.py

# Run simple test runner
python test_runner.py
```

### Option 2: All Tests at Once
```bash
# Run all test files sequentially
python test_mock_packages.py && \
python test_integration_mocks.py && \
python test_cli_integration.py && \
python test_runner.py
```

### Option 3: With pytest (if available)
```bash
# Run with pytest for more detailed output
pytest test_mock_packages.py -v
pytest test_integration_mocks.py -v
pytest test_cli_integration.py -v
```

## Mock Package Infrastructure

### MockPackage Class
The `MockPackage` class extends the base `Package` class to provide:
- Configurable metadata and dependencies
- Simulated installation states
- Mock fetch/download operations
- Controllable upgrade availability
- No external dependencies

### Platform Mocking
All tests mock the OpenFOAM platform dependencies:
- `platform_path()` returns temporary directories
- `installed.json` management with proper version format
- No requirement for OpenFOAM environment variables

### Test Isolation
Each test function/class:
- Creates clean temporary environments
- Manages mock package instances independently
- Cleans up state between tests
- Uses separate mock directories

## Key Test Scenarios

### Cycle Detection Verification
```python
# Tests verify the _detect_cycles method correctly identifies:
- Simple cycles: A → B → A
- Complex cycles: A → B → C → A  
- Self-cycles: A → A
- Diamond patterns without cycles: A → B,C; B → D; C → D
```

### Dependency Resolution Testing
```python
# Tests verify resolve() method handles:
- Simple packages without dependencies
- Packages with multiple dependencies
- Upgrade vs. non-upgrade scenarios
- Force reinstall conditions
- Reverse dependency propagation
```

### Edge Case Coverage
```python
# Tests verify edge cases like:
- Packages already installed (should skip unless upgrade)
- Mixed installation states in dependency chains
- Upgrade available vs. force reinstall logic
- Proper error reporting for cycles
```

## Benefits of Mock Testing

1. **No External Dependencies**: Tests run without OpenFOAM or network access
2. **Deterministic**: Same results every time, no external variables
3. **Fast Execution**: No network delays or actual package operations
4. **Comprehensive Coverage**: Can test error conditions easily
5. **Platform Independent**: Works on any system with Python
6. **Easy Debugging**: Full control over package states and metadata

## Test Output

All tests provide clear output indicating:
- ✅ Passed tests with descriptive messages
- ❌ Failed tests with error details and stack traces
- 🔁 Progress indicators for long-running operations
- Detailed cycle detection messages when cycles are found

The tests are designed to be self-documenting and provide clear feedback about what functionality is being verified.