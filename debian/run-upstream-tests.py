# Run every upstream test against the extension built for this interpreter.
from pathlib import Path
import runpy
import sys
import sysconfig

root = Path(__file__).resolve().parents[1]
suffix = sysconfig.get_config_var('EXT_SUFFIX')
extensions = list((root / 'build').glob('lib*/lxml/etree' + suffix))
if len(extensions) != 1:
    raise SystemExit('expected exactly one extension build for the selected ABI')
build = extensions[0].parent.parent.resolve()
sys.path.insert(0, str(build))
import lxml
import lxml.html
from lxml import etree, objectify

for module in (etree, objectify):
    if not Path(module.__file__).resolve().is_relative_to(build):
        raise SystemExit('refusing to test an installed or foreign extension')
lxml.__path__.append(str(root / 'src/lxml'))
lxml.html.__path__.append(str(root / 'src/lxml/html'))
sys.argv = [str(root / 'test.py'), '--no-src', '--all-levels', '-u', '-f', '-v']
runpy.run_path(str(root / 'test.py'), run_name='__main__')
