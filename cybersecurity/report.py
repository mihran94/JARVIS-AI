"""The findings a defensive check can report.

WHAT THIS IS
    A cybersecurity check returns findings, not text. A finding says what
    was found, how serious it is, what was actually observed, and what
    the owner can do about it. The owner reads the same words every
    time, whatever produced them.

WHAT THIS IS NOT
    * It is not a scanner that invents risk. A check that could not run
      says so and produces no finding.
    * It is not a place for secrets. Everything that goes into a finding
      is redacted first, so a key, a token or a password never reaches
      the report, the screen or the exported file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

#: The severities a finding can carry, from least to most serious.
SEVERITIES = ('info', 'low', 'medium', 'high')

#: The order the findings are shown in, most serious first.
SEVERITY_ORDER = {name: index for index, name in enumerate(reversed(SEVERITIES))}

#: The patterns that are masked before anything is shown or written.
_SECRET_PATTERNS = (
    (r'(?i)\b(sk-[A-Za-z0-9_\-]{12,})', 'sk-…'),
    (r'(?i)\b(ghp_[A-Za-z0-9]{20,})', 'ghp_…'),
    (r'(?i)\b(AKIA[0-9A-Z]{12,})', 'AKIA…'),
    (r'(?i)\b(AIza[0-9A-Za-z_\-]{20,})', 'AIza…'),
    (r'(?i)\b(xox[baprs]-[A-Za-z0-9\-]{8,})', 'xox…'),
    (r'(?i)(api[_ -]?key\s*[=:]\s*)\S+', r'\1<redacted>'),
    (r'(?i)(password\s*[=:]\s*)\S+', r'\1<redacted>'),
    (r'(?i)(secret\s*[=:]\s*)\S+', r'\1<redacted>'),
    (r'(?i)(bearer\s+)[A-Za-z0-9._\-]{10,}', r'\1<redacted>'),
)


def redact(value) -> str:
    """Mask anything that looks like a credential."""
    import re

    text = '' if value is None else str(value)
    for pattern, replacement in _SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text


@dataclass(frozen=True)
class Finding:
    """One thing the check found."""

    severity: str
    category: str
    title: str
    detail: str = ''
    evidence: str = ''
    recommendation: str = ''
    source: str = ''

    def __post_init__(self):
        if self.severity not in SEVERITIES:
            raise ValueError(f'Unknown severity: {self.severity}')

    def as_dict(self) -> dict:
        return {
            'severity': self.severity,
            'category': self.category,
            'title': redact(self.title),
            'detail': redact(self.detail),
            'evidence': redact(self.evidence),
            'recommendation': redact(self.recommendation),
            'source': redact(self.source),
        }

    def as_text(self) -> str:
        """The finding as the owner reads it."""
        parts = [f'[{self.severity.upper()}] {self.title}']
        if self.detail:
            parts.append(self.detail)
        if self.evidence:
            parts.append(f'What was observed: {self.evidence}')
        if self.recommendation:
            parts.append(f'What you can do: {self.recommendation}')
        if self.source:
            parts.append(f'Checked by: {self.source}')
        return redact('\n'.join(parts))


@dataclass
class SecurityReport:
    """Everything one run of the cybersecurity interface found."""

    scope: str = 'Local device'
    created: str = ''
    findings: list = field(default_factory=list)
    checks_run: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def add(self, finding: Finding):
        self.findings.append(finding)

    def extend(self, findings):
        self.findings.extend(findings)

    def ordered(self) -> list:
        """The findings, most serious first."""
        return sorted(self.findings,
                      key=lambda item: (SEVERITY_ORDER.get(item.severity, 0), item.category,
                                        item.title))

    def counts(self) -> dict:
        """How many of each severity."""
        counts = {name: 0 for name in SEVERITIES}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def summary(self) -> str:
        """One line the owner can read at a glance."""
        counts = self.counts()
        parts = [f'{counts[name]} {name}' for name in reversed(SEVERITIES) if counts.get(name)]
        if not parts:
            return 'No findings.'
        return ', '.join(parts) + f' — {len(self.findings)} finding(s) from ' \
                            f'{len(self.checks_run)} check(s).'

    def as_text(self) -> str:
        """The whole report, as the owner reads it."""
        lines = [f'JARVIS Cybersecurity · {self.scope}',
                 f'Taken {self.created or datetime.now(timezone.utc).isoformat(timespec="seconds")}',
                 self.summary(), '']
        if self.checks_run:
            lines.append('Checks run: ' + ', '.join(self.checks_run))
            lines.append('')
        for finding in self.ordered():
            lines.append(finding.as_text())
            lines.append('')
        for note in self.notes:
            lines.append(redact(note))
        if not self.findings:
            lines.append('Nothing was found by the checks that ran.')
        return redact('\n'.join(lines))

    def as_dict(self) -> dict:
        return {
            'scope': self.scope,
            'created': self.created,
            'checks_run': list(self.checks_run),
            'notes': [redact(note) for note in self.notes],
            'findings': [finding.as_dict() for finding in self.findings],
        }


__all__ = ['Finding', 'SEVERITIES', 'SEVERITY_ORDER', 'SecurityReport', 'redact']
