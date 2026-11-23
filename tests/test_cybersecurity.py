"""The Cybersecurity interface: scoped checks, real findings and redaction.

WHAT IS COVERED
    * The checks that can run on this machine return real findings, and
      the ones that cannot say so instead of reporting nothing.
    * A finding carries a severity, what was observed, and what the
      owner can do about it.
    * A secret never reaches a finding, the report text or the exported
      file.
    * The report lists the most serious finding first and counts each
      severity.
    * The interface is separate: no mission tool reaches it, and the
      checks go through the one-use approval gateway.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from core.store import Store
from cybersecurity.diagnostics import (
    CHECKS, CheckUnavailable, check_jarvis_configuration, check_listeners,
    check_processes, run_check,
)
from cybersecurity.report import Finding, SecurityReport, redact


# ── the redaction ──────────────────────────────────────────────────────────

def test_a_key_is_masked():
    assert 'sk-abcdefghijklmnopqrst' not in redact('the key is sk-abcdefghijklmnopqrst')
    assert 'AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ' not in redact('AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ')
    assert 'AKIAIOSFODNN7EXAMPLE' not in redact('AKIAIOSFODNN7EXAMPLE')


def test_a_password_is_masked():
    assert 'hunter2' not in redact('password=hunter2')
    assert 'secretvalue' not in redact('api_key: secretvalue')


def test_a_bearer_token_is_masked():
    assert 'abcdef1234567890' not in redact('Bearer abcdef1234567890')


def test_ordinary_text_is_left_alone():
    assert redact('the launch is on Friday') == 'the launch is on Friday'


# ── the findings ───────────────────────────────────────────────────────────

def test_a_finding_reads_as_words():
    finding = Finding('medium', 'Startup', 'Something starts with Windows',
                      'It runs every time.', evidence='evidence here',
                      recommendation='Remove it.', source='the registry')
    text = finding.as_text()
    assert '[MEDIUM]' in text
    assert 'What was observed: evidence here' in text
    assert 'What you can do: Remove it.' in text


def test_an_unknown_severity_is_refused():
    with pytest.raises(ValueError):
        Finding('catastrophic', 'Anything', 'A title')


def test_the_report_counts_each_severity():
    report = SecurityReport()
    report.add(Finding('high', 'Network', 'One'))
    report.add(Finding('low', 'Network', 'Two'))
    report.add(Finding('low', 'Network', 'Three'))
    counts = report.counts()
    assert counts['high'] == 1
    assert counts['low'] == 2
    assert counts['medium'] == 0


def test_the_report_puts_the_serious_finding_first():
    report = SecurityReport()
    report.add(Finding('low', 'Network', 'A small thing'))
    report.add(Finding('high', 'Firewall', 'A serious thing'))
    assert report.ordered()[0].title == 'A serious thing'


def test_the_report_text_has_no_secret():
    report = SecurityReport()
    report.add(Finding('high', 'Credentials', 'A key', evidence='sk-abcdefghijklmnopqrst'))
    assert 'sk-abcdefghijklmnopqrst' not in report.as_text()


# ── the checks ─────────────────────────────────────────────────────────────

def test_the_listening_check_reports_what_is_listening():
    findings = check_listeners()
    assert findings
    assert findings[0].category == 'Network'
    assert findings[0].severity in ('info', 'low', 'medium', 'high')


def test_the_running_program_check_reports_real_programs():
    findings = check_processes()
    assert findings
    assert 'program' in findings[0].title.lower()


def test_a_check_that_cannot_run_says_so():
    from cybersecurity.diagnostics import check_firewall

    if os.name != 'nt':
        with pytest.raises(CheckUnavailable):
            check_firewall()


def test_running_a_check_that_does_not_exist_is_refused():
    with pytest.raises(ValueError):
        run_check('no_such_check')


def test_every_check_has_a_title_and_a_description():
    for name, (title, description, function) in CHECKS.items():
        assert title and description
        assert callable(function)


# ── the JARVIS configuration review ────────────────────────────────────────

def test_the_configuration_review_finds_automatic_updates(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    store.set('auto_maintenance', True)
    findings = check_jarvis_configuration(store)
    assert any('source updates' in finding.title for finding in findings)


def test_the_configuration_review_finds_the_backup_consent(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    store.set('backup_consent', True)
    findings = check_jarvis_configuration(store)
    assert any('backup' in finding.title.lower() for finding in findings)


def test_a_clean_configuration_reports_one_finding(tmp_path):
    store = Store(tmp_path / 'history.sqlite3')
    findings = check_jarvis_configuration(store)
    assert len(findings) == 1
    assert findings[0].severity == 'info'


# ── the interface ──────────────────────────────────────────────────────────

def test_the_interface_is_a_separate_page_and_asks_before_it_checks(tmp_path):
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        assert 'Cybersecurity' in window.page_indices
        page = window.cybersecurity_panel
        asked = []
        window.confirm = lambda action: asked.append(action) or True
        page.checks.setCurrentRow(0)
        page.run_selected()
        assert asked, 'the check did not ask for approval'
        assert asked[0].kind == 'security_check'
        assert page.output.toPlainText()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_a_refused_check_runs_nothing(tmp_path):
    from desktop.app import Window

    app = QApplication.instance() or QApplication([])
    window = Window(tmp_path)
    try:
        page = window.cybersecurity_panel
        window.confirm = lambda action: False
        page.checks.setCurrentRow(0)
        page.run_selected()
        assert not page.report.findings
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
