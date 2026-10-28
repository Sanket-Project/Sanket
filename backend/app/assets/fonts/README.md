# Report font sources and license

The four `NotoSans*-Regular.ttf` inputs are unchanged Noto Project font files from
`https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf`.
`OFL.txt` retains the upstream copyright and SIL Open Font License 1.1.

The three `SanketReportSans*-Regular.ttf` files are modified OFL fonts combining
Noto Sans Latin coverage with Devanagari, Telugu, or Tamil coverage. Their family,
full, unique, and PostScript name records are renamed to **SANKET Report Sans**.
They remain licensed under the SIL OFL 1.1. No font is sold separately.

Mixed-font shaping in ReportLab corrupted Latin currency codes and punctuation
beside Indic text. One composite font per paragraph lets HarfBuzz shape the full
paragraph without crossing font glyph namespaces. Source-link paragraphs use
unshaped Latin Noto Sans.

Reproduce from the included input font files, from `backend/`:

```powershell
uv run --with fonttools==4.67.0 python app/assets/fonts/build_report_fonts.py
```

The script preserves source timestamps, renames modified font identities, and
updates `report-fonts.json` with tool version and input/output SHA-256 hashes.
`fontTools` is a build-only tool; the application uses the bundled TTF files,
ReportLab, and HarfBuzz from the declared `reportlab[shaping]` dependency.
