"""Regression checks for stale or incomplete acceptance evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('submission_edge_report', ROOT/'scripts/evaluate_submission_edges.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


def evidence(tmp_path, names=None):
    root = ET.Element('testsuite')
    for name in names or reporter.EXPECTED_TESTS:
        case = ET.SubElement(root, 'testcase', name=name, time='1')
        properties = ET.SubElement(case, 'properties')
        ET.SubElement(properties, 'property', name='edge_evidence', value=json.dumps({
            'family': reporter.EXPECTED_TESTS[name], 'expected': {}, 'observed': {},
        }))
    xml = tmp_path/'junit.xml'
    ET.ElementTree(root).write(xml)
    saved = {'source_sha256': {'historical.py': 'original-run-hash'},
        'runtime_provenance': {'test_image': 'original-image'},
        'started_at_utc': '2026-11-11T00:00:00+00:00',
        'sources_unchanged_during_run': True,
        'junit_sha256': hashlib.sha256(xml.read_bytes()).hexdigest()}
    (tmp_path/'run-inputs.json').write_text(json.dumps(saved))
    return xml, saved


def test_archived_summary_preserves_original_code_identity(tmp_path):
    xml, saved = evidence(tmp_path)
    loaded = reporter.load_run_inputs(xml)
    report = reporter.report(xml, tmp_path/'report.json', loaded)
    assert report['all_passed']
    assert report['source_sha256'] == saved['source_sha256']
    assert report['runtime_provenance'] == saved['runtime_provenance']


def test_modified_junit_cannot_reuse_original_run_provenance(tmp_path):
    xml, _ = evidence(tmp_path)
    xml.write_text(xml.read_text()+'\n')
    with pytest.raises(SystemExit, match='differs from the recorded run'):
        reporter.load_run_inputs(xml)


def test_missing_original_provenance_requires_a_new_run(tmp_path):
    xml, _ = evidence(tmp_path)
    (tmp_path/'run-inputs.json').unlink()
    with pytest.raises(SystemExit, match='Original run-inputs.json is required'):
        reporter.load_run_inputs(xml)


def test_repeated_passing_case_cannot_replace_an_omitted_case(tmp_path):
    names = list(reporter.EXPECTED_TESTS)
    names[-1] = names[0]
    xml, saved = evidence(tmp_path, names)
    result = reporter.report(xml, tmp_path/'report.json', saved)
    assert result['total'] == result['passed'] == 11
    assert not result['all_passed']
