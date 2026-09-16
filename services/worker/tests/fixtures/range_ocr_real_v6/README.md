# Real range OCR regression corpus v1

This checksum-bound corpus contains four user-supplied screenshots prepared on
2026-09-02. File names are deliberately neutral and do not encode a range.
External browser/Admin chrome and every visible `seq_*` filename were redacted
while preserving the original 720×1280 canvas. The OCR runtime must therefore
derive any result only from labels visible on the game screen.

`screen-a.jpg`, `screen-b.jpg`, and `screen-c.jpg` are human-readable exact
examples. `transition-d.jpg` shows two conflicting neighbouring screens and is
an anti-false-positive fixture: it must never become an automatic exact range.

The corpus is a regression gate, not a representative recall benchmark. Its
manifest is the source of truth for checksum, dimensions, redaction regions and
human labels.
