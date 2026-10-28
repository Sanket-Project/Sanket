"""Rebuild OFL-derived SANKET Report Sans fonts.

Run from backend: uv run --with fonttools==4.67.0 python app/assets/fonts/build_report_fonts.py
The runtime needs only the generated TTF files, not fontTools.
"""
from pathlib import Path
import hashlib
import json
import fontTools
from fontTools.merge import Merger

root = Path(__file__).parent
records = []
for script in ("Devanagari", "Telugu", "Tamil"):
    sources = [root / "NotoSans-Regular.ttf", root / f"NotoSans{script}-Regular.ttf"]
    font = Merger().merge([str(path) for path in sources])
    family = f"SANKET Report Sans {script}"
    names = {1: family, 2: "Regular", 3: f"{family} Regular 1.0", 4: f"{family} Regular", 6: f"SANKETReportSans{script}-Regular"}
    # Rename every existing name-table platform record for modified font identity.
    for record in font["name"].names:
        if record.nameID in names:
            record.string = names[record.nameID].encode(record.getEncoding())
    output = root / f"SanketReportSans{script}-Regular.ttf"
    font.recalcTimestamp = False
    font.save(output)
    records.append({"output": output.name, "family": family, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "sources": [{"filename": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()} for source in sources]})
(root / "report-fonts.json").write_text(json.dumps({"fontTools": fontTools.__version__, "license": "SIL OFL-1.1",
    "upstream": "https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf", "fonts": records}, indent=2), encoding="utf-8")
print("Built three renamed OFL Latin/Indic report fonts")
