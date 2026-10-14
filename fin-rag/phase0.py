"""
Phase 0: parse one annual report, print its tables, find the revenue line.

Usage:
    python phase0.py report.pdf                 # whole document (slow on CPU for 200+ pages)
    python phase0.py report.pdf 180 200         # only pages 180-200 (the financial statements)
"""
import sys
import csv
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from docling.document_converter import DocumentConverter

REVENUE_KEYWORDS = ["revenue from operations", "total revenue", "net sales", "revenue"]


def slice_pdf(src: Path, start: int, end: int) -> Path:
    """Write pages start..end (1-based, inclusive) to a smaller PDF so parsing is fast."""
    reader, writer = PdfReader(src), PdfWriter()
    for i in range(start - 1, min(end, len(reader.pages))):
        writer.add_page(reader.pages[i])
    out = src.with_name(f"{src.stem}_p{start}-{end}.pdf")
    with open(out, "wb") as f:
        writer.write(f)
    return out


def main():
    src = Path(sys.argv[1])
    offset = 0
    if len(sys.argv) == 4:
        start, end = int(sys.argv[2]), int(sys.argv[3])
        src = slice_pdf(src, start, end)
        offset = start - 1  # map sliced page numbers back to the original

    print(f"Parsing {src} ...")
    doc = DocumentConverter().convert(str(src)).document
    print(f"Found {len(doc.tables)} tables\n")

    hits = []
    for t_idx, table in enumerate(doc.tables):
        try:
            df = table.export_to_dataframe(doc=doc)
        except TypeError:  # older docling versions take no argument
            df = table.export_to_dataframe()
        page = (table.prov[0].page_no + offset) if table.prov else None

        print(f"--- Table {t_idx} (page {page}) shape={df.shape}")
        print(df.head(8).to_string()[:1500], "\n")

        for _, row in df.iterrows():
            label = str(row.iloc[0]).strip().lower()
            if any(k in label for k in REVENUE_KEYWORDS):
                values = [str(v) for v in row.iloc[1:].tolist()]
                hits.append({"page": page, "table": t_idx, "label": label, "values": " | ".join(values)})

    print("=== Revenue candidates ===")
    for h in hits:
        print(h)

    with open("metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["page", "table", "label", "values"])
        w.writeheader()
        w.writerows(hits)
    print(f"\nWrote {len(hits)} rows to metrics.csv")


if __name__ == "__main__":
    main()
