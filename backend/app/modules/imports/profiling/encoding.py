"""Bounded encoding detection and decoding."""

from __future__ import annotations

import codecs
from dataclasses import dataclass

from charset_normalizer import from_bytes

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity


@dataclass(frozen=True, slots=True)
class DecodedSample:
    text: str
    encoding: str
    issues: tuple[ImportIssue, ...]


def decode_sample(data: bytes) -> DecodedSample:
    issues: list[ImportIssue] = []
    payload = data
    if payload.startswith(codecs.BOM_UTF8):
        encoding = "utf-8"
        payload = payload[len(codecs.BOM_UTF8) :]
    elif payload.startswith(codecs.BOM_UTF16_LE):
        encoding = "utf-16-le"
        payload = payload[len(codecs.BOM_UTF16_LE) :]
    elif payload.startswith(codecs.BOM_UTF16_BE):
        encoding = "utf-16-be"
        payload = payload[len(codecs.BOM_UTF16_BE) :]
    else:
        match = from_bytes(payload).best()
        if match is None or match.encoding is None or match.chaos > 0.2:
            encoding = "utf-8"
            issues.append(
                ImportIssue(
                    code=IssueCode.ENCODING_UNCERTAIN,
                    severity=IssueSeverity.WARNING,
                    message="Encoding could not be determined confidently; UTF-8 was used.",
                )
            )
        else:
            encoding = match.encoding

    text = payload.decode(encoding, errors="replace")
    if "\ufffd" in text:
        issues.append(
            ImportIssue(
                code=IssueCode.ENCODING_REPLACEMENT,
                severity=IssueSeverity.WARNING,
                message="Undecodable bytes were replaced while reading the sample.",
            )
        )
    return DecodedSample(text=text, encoding=encoding.lower(), issues=tuple(issues))
