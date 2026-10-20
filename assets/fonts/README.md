# Fonts

The session summary PDF (`src/export_pdf.py`, T5.2) uses **DejaVu Sans** and **DejaVu Sans Bold**, version 2.37. ReportLab's own fonts have no Greek letters, and an approved source title has "β" ("β-hydroxy-β-methylbutyrate").

- **Source:** the official release `dejavu-fonts-ttf-2.37.zip` (published 2016-07-30), https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37, downloaded on 2026-10-20 with the owner's approval. Only the two files below and the licence were copied from it, unchanged.
- **Licence:** `LICENSE` in this folder, copied unchanged from the release. The fonts are © Bitstream (Bitstream Vera licence) with glyphs from the Arev fonts © Tavmjong Bah (same terms); the DejaVu changes are in the public domain. The licence allows using, copying and redistributing the fonts, bundled with software, as long as this notice goes with them and the fonts are not sold by themselves. It is checked against `.claude/rules/copyright.md` rule 9 in `docs/ARCHITECTURE.md` section 12. Every PDF embeds subsets of the fonts, so its Credits end with the part of `LICENSE` for DejaVu Sans (the Bitstream Vera and Arev notices), printed word for word from this file (`export_pdf.font_licence_paragraphs()`); keep `LICENSE` unchanged.

| File | SHA-256 |
|---|---|
| `DejaVuSans.ttf` | `7da195a74c55bef988d0d48f9508bd5d849425c1770dba5d7bfc6ce9ed848954` |
| `DejaVuSans-Bold.ttf` | `e6476c1b80502924294eed40894c5b18e06c181444ca953e5334262df9c27724` |
