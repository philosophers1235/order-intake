"""Rebuild the spreadsheet sample. The scans and PDFs are committed as they are."""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

out = Path(__file__).resolve().parent.parent / "samples/ricambi-lazio/inbox/ordine-prati.xlsx"

book = Workbook()
sheet = book.active
sheet.title = "Ordine"
sheet.append(["Autofficina Prati snc"])
sheet.append(["Ordine n. 118 del 15/10/2026"])
sheet.append([])
sheet.append(["Codice", "Descrizione", "Q.tà"])
for cell in sheet[4]:
    cell.font = Font(bold=True)
for row in [
    ("FA-220", "Filtro aria", 4),
    ("BA 70", "Batteria 70Ah", 1),
    ("FO-3l6", "Filtro olio", 5),
    ("", "Liquido freni DOT 4", 6),
]:
    sheet.append(row)
sheet.column_dimensions["B"].width = 28
book.save(out)
print(out)
