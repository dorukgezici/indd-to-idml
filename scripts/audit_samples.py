"""Audit local samples against the layered import, without claiming Adobe parity."""
import hashlib
import json
import zipfile
from pathlib import Path
from lxml import etree
from psd_tools import PSDImage
from indd_to_idml.idml import validate

root = Path(__file__).resolve().parents[1]
summary = []
for source in sorted((root / 'in').rglob('*.indd')):
    output = root / 'out' / source.relative_to(root / 'in').with_suffix('.idml')
    report = json.loads(output.with_suffix('.report.json').read_text())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == report['source']['sha256'], 'Source changed'
    psd = PSDImage.open(root / '.cache/indd-to-idml' / (digest + '.psd'), max_alloc_bytes=1024**3)
    source_texts = [l.text.replace('\x00', '').replace('\r', '\n') for a in psd for l in a.descendants() if l.kind == 'type']
    with zipfile.ZipFile(output) as z:
        manifest = etree.fromstring(z.read('designmap.xml'))
        texts = []
        for part in manifest:
            if etree.QName(part).localname != 'Story': continue
            story = etree.fromstring(z.read(part.get('src')))
            texts.append(''.join(e.text or '' if e.tag == 'Content' else '\n' for e in story.iter() if e.tag in {'Content', 'Br'}))
        assert source_texts == texts, 'Text differs from layered import'
    assert len(psd) == report['validation']['pages']
    assert not report['rasterized_objects']
    result = {'document': source.name, **validate(output), 'all_imported_text_preserved': True,
              'input_sha256_unchanged': True, 'rasterized_objects': 0,
              'restored_original_images': report['restored_original_images'],
              'missing_fonts': report['missing_fonts']}
    summary.append(result)
print(json.dumps(summary, indent=2, ensure_ascii=False))
