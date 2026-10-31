"""Actual shared parser/XPath/XSLT/schema and cross-thread XML ownership checks."""
from concurrent.futures import ThreadPoolExecutor
import copy
import gc
import json
import sys
import threading

assert not sys._is_gil_enabled()
from lxml import etree, objectify
assert not sys._is_gil_enabled() and etree._freethreading_enabled

parser = etree.XMLParser(no_network=True, resolve_entities=False)
xpath = etree.XPath('sum(/root/n)')
schema = etree.XMLSchema(etree.XML(b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="root"><xs:complexType><xs:sequence><xs:element name="n" type="xs:int" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:schema>'''))
relaxng = etree.RelaxNG(etree.XML(b'''<element name="root" xmlns="http://relaxng.org/ns/structure/1.0"><oneOrMore><element name="n"><text/></element></oneOrMore></element>'''))
transform = etree.XSLT(etree.XML(b'''<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"><xsl:template match="/"><sum><xsl:value-of select="sum(/root/n)"/></sum></xsl:template></xsl:stylesheet>'''))
callback_threads = set()
callback_lock = threading.Lock()

def callback(context, value):
    assert not sys._is_gil_enabled()
    with callback_lock:
        callback_threads.add(threading.get_native_id())
    return value * 2

with_callback = etree.XPath('t:twice(sum(/root/n))', namespaces={'t': 'urn:owned-test'}, extensions={('urn:owned-test', 'twice'): callback})
start = threading.Barrier(8)

def worker(seed):
    start.wait(timeout=30)
    for offset in range(64):
        number = seed * 64 + offset
        document = etree.fromstring(f'<root><n>{number}</n><n>3</n></root>'.encode(), parser)
        assert xpath(document) == number + 3
        assert with_callback(document) == (number + 3) * 2
        schema.assertValid(document)
        relaxng.assertValid(document)
        assert transform(document).getroot().text == str(number + 3)
        cloned = copy.deepcopy(document)
        detached = cloned[0]
        cloned.remove(detached)
        document.append(detached)
        del cloned
        gc.collect(0)
        assert detached.getparent() is document and int(detached.text) == number
        assert etree.fromstring(etree.tostring(document))[2].text == str(number)
        value = objectify.fromstring(b'<value><n>42</n></value>')
        assert value.n.pyval == 42
        try:
            etree.fromstring(b'<root>', parser)
        except etree.XMLSyntaxError as error:
            assert error.position[0] == 1
        else:
            raise AssertionError('Expected the actual parser error')
    return document[0]

with ThreadPoolExecutor(max_workers=8) as pool:
    transferred = list(pool.map(worker, range(8)))
gc.collect()
assert all(element.getroottree().getroot().tag == 'root' for element in transferred)
assert len(callback_threads) == 8
assert not sys._is_gil_enabled()
print(json.dumps({'status': 'PASS', 'python': sys.version, 'GIL': False, 'lxml': etree.LXML_VERSION, 'libxml2': etree.LIBXML_VERSION, 'libxslt': etree.LIBXSLT_VERSION, 'threaded_documents': 512, 'callback_native_threads': len(callback_threads), 'shared_parser_XPath_XSLT_XMLSchema_RelaxNG': 'PASS', 'cross_thread_ownership_and_real_errors': 'PASS'}))
