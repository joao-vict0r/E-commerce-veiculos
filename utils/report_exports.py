from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def build_simple_pdf(lines: list[str]) -> bytes:
    safe_lines = [
        (line or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in lines
    ]
    content_lines = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for idx, line in enumerate(safe_lines):
        if idx == 0:
            content_lines.append(f"({line}) Tj")
        else:
            content_lines.append("T*")
            content_lines.append(f"({line}) Tj")
    content_lines.append("ET")
    stream_text = "\n".join(content_lines)
    stream_bytes = stream_text.encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n")
    objects.append(f"4 0 obj << /Length {len(stream_bytes)} >> stream\n".encode("latin-1") + stream_bytes + b"\nendstream endobj\n")
    objects.append(b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    xref_positions = [0]
    for obj in objects:
        xref_positions.append(len(out))
        out.extend(obj)

    xref_start = len(out)
    out.extend(f"xref\n0 {len(xref_positions)}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for pos in xref_positions[1:]:
        out.extend(f"{pos:010d} 00000 n \n".encode("latin-1"))

    out.extend(
        f"trailer << /Size {len(xref_positions)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1")
    )
    return bytes(out)


def report_lines_for_type(report_type: str, reports: dict) -> list[str]:
    report_type = (report_type or "resumo").strip().lower()

    if report_type == "metas":
        lines = [
            "Relatorio de Meta de Vendedores",
            f"Data inicial: {reports.get('start_date') or '-'}",
            f"Data final: {reports.get('end_date') or '-'}",
            "",
        ]
        for item in reports.get("seller_goals_report", []):
            target = item.get("target", 0)
            target_text = str(target) if target else "-"
            progress_text = f"{item.get('progress', 0):.1f}%" if target else "-"
            lines.append(
                f"- {item.get('seller_name')}: vendas={item.get('sold_qty', 0)}, meta={target_text}, atingimento={progress_text}"
            )
        if len(lines) == 4:
            lines.append("Sem dados de metas.")
        return lines

    if report_type == "carros":
        return [
            "Relatorio de Carros",
            f"Marca: {reports.get('car_brand') or 'Todas'}",
            f"Data inicial: {reports.get('car_start_date') or '-'}",
            f"Data final: {reports.get('car_end_date') or '-'}",
            "",
            f"Carros vendidos: {reports.get('vehicles_sold_total', 0)}",
            f"Carros cadastrados atuais: {reports.get('vehicles_registered_total', 0)}",
            f"Carros disponiveis: {reports.get('vehicles_available_total', 0)}",
        ]

    return [
        "Relatorio de Total de Vendas",
        f"Data inicial: {reports.get('start_date') or '-'}",
        f"Data final: {reports.get('end_date') or '-'}",
        "",
        f"Total de vendas (R$): {reports.get('sales_total_value', 0):.2f}",
        f"Quantidade de vendas: {reports.get('sales_qty', 0)}",
    ]


def build_xlsx_bytes(reports: dict, report_type: str) -> bytes:
    def col_letter(idx: int) -> str:
        s = ""
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            s = chr(65 + rem) + s
        return s

    def xml_escape(value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def make_sheet(rows: list[list]) -> str:
        row_xml = []
        for r_idx, row in enumerate(rows, start=1):
            cells = []
            for c_idx, val in enumerate(row, start=1):
                cell_ref = f"{col_letter(c_idx)}{r_idx}"
                if isinstance(val, (int, float)):
                    cells.append(f'<c r="{cell_ref}"><v>{val}</v></c>')
                else:
                    cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(val)}</t></is></c>')
            row_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>' + ''.join(row_xml) + '</sheetData></worksheet>'
        )

    report_type = (report_type or "resumo").strip().lower()

    if report_type == "metas":
        rows1 = [["Vendedor", "Vendas no período", "Meta", "Atingimento (%)"]]
        for item in reports.get("seller_goals_report", []):
            rows1.append([
                item.get("seller_name") or "",
                int(item.get("sold_qty") or 0),
                int(item.get("target") or 0),
                round(float(item.get("progress") or 0), 2),
            ])
        rows2 = [["Filtro", "Valor"], ["Data inicial", reports.get("start_date") or "-"], ["Data final", reports.get("end_date") or "-"]]
        sheet1_name, sheet2_name = "Metas", "Filtro"
    elif report_type == "carros":
        rows1 = [
            ["Métrica", "Valor"],
            ["Carros vendidos", int(reports.get("vehicles_sold_total") or 0)],
            ["Carros cadastrados atuais", int(reports.get("vehicles_registered_total") or 0)],
            ["Carros disponíveis", int(reports.get("vehicles_available_total") or 0)],
        ]
        rows2 = [["Filtro", "Valor"], ["Marca", reports.get("car_brand") or "Todas"], ["Data inicial", reports.get("car_start_date") or "-"], ["Data final", reports.get("car_end_date") or "-"]]
        sheet1_name, sheet2_name = "Carros", "Filtro"
    else:
        rows1 = [
            ["Métrica", "Valor"],
            ["Total de vendas (R$)", float(reports.get("sales_total_value") or 0)],
            ["Quantidade de vendas", int(reports.get("sales_qty") or 0)],
        ]
        rows2 = [["Filtro", "Valor"], ["Data inicial", reports.get("start_date") or "-"], ["Data final", reports.get("end_date") or "-"]]
        sheet1_name, sheet2_name = "Vendas", "Filtro"

    sheet1 = make_sheet(rows1)
    sheet2 = make_sheet(rows2)

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

    rels_root = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{sheet1_name}" sheetId="1" r:id="rId1"/>
    <sheet name="{sheet2_name}" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>'''

    wb_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''

    mem = BytesIO()
    with ZipFile(mem, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels_root)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/styles.xml", styles)
        zf.writestr("xl/worksheets/sheet1.xml", sheet1)
        zf.writestr("xl/worksheets/sheet2.xml", sheet2)
    return mem.getvalue()
