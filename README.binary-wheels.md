# Experimental CPython 3.15t dependency wheels

Ordinary pip from the default branch selects the exact, hash-checked original
CPython 3.15t artifact for Windows x64 or Linux x86_64 with glibc 2.39+.
Native XML sources are upstream lxml 7.0.0b1, commit
0117cfefe3dec30cede602ddda70dd6eb1e98f35, including the substantive document,
parser, XPath and XSLT free-threading implementation. No GIL override is used.

Windows uses the official lxml SDK (libxml2 2.11.9, libxslt 1.1.45), Linux uses
statically built libxml2 2.15.4 and libxslt 1.1.45. Both include actual iconv and
zlib support. Upstream libxml2 versions expose different optional features;
original test skips are retained and recorded without changing test assertions.
No GLib or D-Bus substitute is part of lxml.

The build fix retains LXML_LOCK_PERFORMANCE=1 for the original _testlock extension
when repeated PEP 517 hooks reuse generated C and therefore omit Cython's build
metadata. The production XML extensions retain their original macros and code.
Both delivered wheels passed the complete original suite, the real native test
instrument, shared parser/XPath/XSLT/XMLSchema/RelaxNG, Python callbacks and
512 documents across eight native threads with natural GIL off.

Changed sources and explicit compiler/SDK options use the original source build.
Windows 3.15t source builds automatically obtain the pinned official SDK archives
in windows_build_sdk.json, verify SHA256, size and ZIP entries, and select the
installed compatible MSVC 14.44 toolset for its /GL static libraries. All build
environment changes are local to the build process and restored afterward.
Other platforms retain upstream source prerequisites. No consumer flags or
global SDK changes are required for qualified binary profiles.

These are engineering dependency artifacts, not a StableKite product release.
