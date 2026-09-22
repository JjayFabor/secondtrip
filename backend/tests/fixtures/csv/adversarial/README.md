# Adversarial CSV fixtures

Small textual cases live here. Tests construct byte-specific cases (UTF-16 BOM, invalid UTF-8,
null bytes, mixed line endings, and workbook/compression magic) directly so Git does not need
opaque binary fixtures. Oversized rows and fields are also generated in tests to keep the
repository small.
