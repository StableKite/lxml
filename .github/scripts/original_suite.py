"""Run unmodified source tests against the actual installed lxml wheel."""
from pathlib import Path
import importlib
import importlib.util
import json
import runpy
import sys
import sysconfig

assert sysconfig.get_config_var('Py_GIL_DISABLED')
assert not sys._is_gil_enabled()
source = Path(sys.argv[1]).resolve(strict=True)
import lxml
import lxml.etree
import lxml.objectify

installed = Path(lxml.__file__).parent
native = {name: str(importlib.import_module(name).__file__) for name in ('lxml.etree', 'lxml.objectify')}
assert all(Path(path).is_relative_to(installed) for path in native.values())
assert lxml.etree._freethreading_enabled
# Only add the original test package; runtime extension imports remain installed.
lxml.__path__.append(str(source / 'src/lxml'))
import lxml.tests
lxml.tests.__path__.append(str(installed / 'tests'))
for test_directory in (source / 'src/lxml').rglob('tests'):
    if test_directory.is_dir() and test_directory.parent != source / 'src/lxml':
        package_name = '.'.join(test_directory.parent.relative_to(source / 'src').parts)
        package = importlib.import_module(package_name)
        package.__path__.append(str(test_directory.parent))
if len(sys.argv) > 2:
    instrument = json.loads(Path(sys.argv[2]).read_text())
    spec = importlib.util.spec_from_file_location('lxml.tests._testlock', instrument['native_test_helper'])
    testlock = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = testlock
    spec.loader.exec_module(testlock)
else:
    testlock = importlib.import_module('lxml.tests._testlock')
    assert Path(testlock.__file__).is_relative_to(installed)
print(json.dumps({'runtime': sys.version, 'natural_GIL': sys._is_gil_enabled(), 'native': native, 'test_lock_native': testlock.__file__, 'test_sources': str(source)}, indent=2), flush=True)
runner = runpy.run_path(str(source / 'test.py'), run_name='original_lxml_test_runner')
original_run = runner['CustomTestRunner'].run
def recorded_run(self, suite):
    result = original_run(self, suite)
    print(json.dumps({'original_tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'existing_skips': len(result.skipped), 'expected_failures': len(result.expectedFailures), 'unexpected_successes': len(result.unexpectedSuccesses), 'GIL_after_suite': sys._is_gil_enabled()}), flush=True)
    return result
runner['CustomTestRunner'].run = recorded_run
code = runner['main']([str(source / 'test.py'), '--no-src', '--all-levels', '-v'])
assert not sys._is_gil_enabled(), 'An imported test dependency enabled the GIL'
raise SystemExit(code)
