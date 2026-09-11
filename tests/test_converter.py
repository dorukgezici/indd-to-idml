import io
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from lxml import etree

from indd_to_idml.indd import MAGIC, inspect_indd
from indd_to_idml.idml import Package, validate, num
from indd_to_idml.convert import Assets, text_paragraphs
from indd_to_idml.cli import main


def indd(path, endian=1):
    data = bytearray(4096)
    data[:16] = MAGIC
    data[16:24] = b'DOCUMENT'
    data[24] = endian
    struct.pack_into(('<' if endian == 1 else '>') + 'II', data, 29, 21, 2)
    path.write_bytes(data)
    return path


@pytest.mark.parametrize('endian', [1, 2])
def test_header_and_source_unchanged(tmp_path, endian):
    source = indd(tmp_path / 'Mayıs.indd', endian)
    original = source.read_bytes()
    assert inspect_indd(source)['version'] == {'major': 21, 'minor': 2}
    assert source.read_bytes() == original


@pytest.mark.parametrize('data', [b'', MAGIC, b'garbage' * 1000])
def test_reject_invalid_inputs(tmp_path, data):
    source = tmp_path / 'bad.indd'
    source.write_bytes(data)
    with pytest.raises(ValueError):
        inspect_indd(source)


def text_layer():
    # A surrogate pair precedes a formatting boundary, followed by Turkish text.
    return SimpleNamespace(text='A😀İ\rB', engine_dict={
        'StyleRun': {'RunLengthArray': [3, 4], 'RunArray': [
            {'StyleSheet': {'StyleSheetData': {'FontSize': 20}}},
            {'StyleSheet': {'StyleSheetData': {'FontSize': 30}}}]},
        'ParagraphRun': {'RunLengthArray': [5, 2], 'RunArray': [
            {'ParagraphSheet': {'Properties': {}}},
            {'ParagraphSheet': {'Properties': {}}}]},
    }, resource_dict={'StyleSheetSet': [{'StyleSheetData': {'Font': 0}}],
                      'FontSet': [{'Name': 'Montserrat-Bold'}]})


def test_unicode_run_boundaries():
    paragraphs, _ = text_paragraphs(text_layer(), {})
    assert [[r['text'] for r in p['runs']] for p in paragraphs] == [['A😀', 'İ'], ['B']]
    assert paragraphs[0]['runs'][1]['break'] is True
    assert paragraphs[0]['runs'][0]['attrs']['PointSize'] == '20'
    assert paragraphs[1]['runs'][0]['attrs']['PointSize'] == '30'


@pytest.fixture
def package(tmp_path):
    p = Package()
    page = p.add_page(600, 800, 1)
    paragraphs, _ = text_paragraphs(text_layer(), {})
    p.add_text(page, 'Unicode <heading>', (1, 0, 0, 1, 20, 40), (0, 0, 500, 120), paragraphs)
    source = tmp_path / 'photo ı.png'
    Image.new('RGB', (10, 20), 'blue').save(source)
    p.add_image(page, 'Rotated image', source, (10, 20), (0, 2, -2, 0, 100, 200), (20, 200, 100, 220))
    p.add_shape(page, 'Curve', [(False, [((0, 0), (0, 0), (10, 20)), ((50, 50), (40, 80), (50, 50))])], None, [0, 0, 0], 2)
    dest = tmp_path / 'document.idml'
    p.finish(dest)
    return dest


def test_native_objects_unicode_and_transforms(package):
    assert validate(package)['text_frames'] == 1
    with zipfile.ZipFile(package) as z:
        story = etree.fromstring(z.read(next(n for n in z.namelist() if n.startswith('Stories/'))))
        assert ''.join(story.xpath('//Content/text()')) == 'A😀İB'
        spread = etree.fromstring(z.read(next(n for n in z.namelist() if n.startswith('Spreads/'))))
        assert spread.find('.//Image').get('ItemTransform') == '0 2 -2 0 100 200'
        assert spread.find('.//Polygon/Properties/PathGeometry/GeometryPathType').get('PathOpen') == 'true'
        assert spread.find('.//TextFrame').get('ParentStory') == story.find('Story').get('Self')


def rewrite(path, change):
    with zipfile.ZipFile(path) as z:
        entries = [(info, z.read(info)) for info in z.infolist()]
    with zipfile.ZipFile(path, 'w') as z:
        for info, data in entries:
            replacement = change(info.filename, data)
            if replacement is not None:
                z.writestr(info, replacement)


@pytest.mark.parametrize('damage,expected', [
    ('mimetype', 'mimetype'), ('part', 'Missing IDML part'),
    ('story', 'Unresolved IDML references'), ('dtd', 'DTD'),
])
def test_reject_broken_packages(package, damage, expected):
    def change(name, data):
        if damage == 'mimetype' and name == 'mimetype': return b'wrong'
        if damage == 'part' and name.startswith('Stories/'): return None
        if damage == 'story' and name.startswith('Spreads/'):
            root = etree.fromstring(data)
            root.find('.//TextFrame').set('ParentStory', 'missing')
            return etree.tostring(root)
        if damage == 'dtd' and name == 'Resources/Styles.xml':
            return data.replace(b'?>', b'?>\n<!DOCTYPE x []>', 1)
        return data
    rewrite(package, change)
    with pytest.raises(ValueError, match=expected): validate(package)


def test_missing_link_fails(package):
    next(package.parent.glob('*.png')).unlink()
    with pytest.raises(ValueError, match='Unresolved image link'): validate(package)


def test_reject_nonfinite_geometry():
    with pytest.raises(ValueError): num(float('nan'))


def test_ambiguous_original_is_not_guessed(tmp_path):
    inputs = tmp_path / 'in'; inputs.mkdir()
    for name in ('a.png', 'b.png'):
        Image.new('RGB', (60, 40), 'red').save(inputs / name)
    raw = io.BytesIO(); Image.new('RGB', (30, 20), 'red').save(raw, format='PNG')
    report = {'assets': []}
    Assets(inputs, tmp_path / 'assets', report).save(raw.getvalue())
    assert report['assets'][0]['restored_from'] is None


def test_cli_does_not_overwrite_or_write_inside_input(tmp_path, monkeypatch):
    inputs = tmp_path / 'in'; inputs.mkdir()
    indd(inputs / 'sample.indd')
    assert main([str(inputs), '-o', str(inputs / 'out')]) == 1
    out = tmp_path / 'out'; out.mkdir()
    existing = out / 'sample.idml'; existing.write_bytes(b'keep me')
    monkeypatch.setattr('indd_to_idml.cli.installed_postscript_names', lambda: set())
    assert main([str(inputs), '-o', str(out)]) == 1
    assert existing.read_bytes() == b'keep me'


def test_corrupt_psd_channels_fail_instead_of_returning_black(tmp_path, monkeypatch):
    import warnings
    from psd_tools.compression import PSDDecompressionWarning
    from indd_to_idml.convert import convert_psd

    def decode(*args):
        warnings.warn('Corrupt channel', PSDDecompressionWarning)
        return {'silently_replaced_with_black': True}

    monkeypatch.setattr('indd_to_idml.convert._convert_psd', decode)
    with pytest.raises(PSDDecompressionWarning):
        convert_psd(tmp_path / 'broken.psd', tmp_path / 'source.indd', tmp_path / 'out.idml', {})
