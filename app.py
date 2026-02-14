from __future__ import annotations

import json
import os
from typing import Any
from datetime import datetime
from urllib import error as urlerror
from urllib import request as urlrequest
from uuid import uuid4

from flask import Flask, redirect, render_template, request, session, url_for

DATA_DIR = os.path.dirname(__file__)
VEHICLES_FILE = os.path.join(DATA_DIR, "vehicles.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SELLERS_FILE = os.path.join(DATA_DIR, "sellers.json")
COMMISSIONS_FILE = os.path.join(DATA_DIR, "commissions.json")
GOALS_FILE = os.path.join(DATA_DIR, "seller_goals.json")
PIX_SETTINGS_FILE = os.path.join(DATA_DIR, "pix_settings.json")

REQUIRED_FIELDS = {
    "marca": "Marca",
    "modelo": "Modelo",
    "ano": "Ano",
    "renavam": "Renavam",
    "placa": "Placa",
    "ipva_vencimento": "Data de vencimento do IPVA",
}


def load_vehicles() -> list[dict[str, Any]]:
    try:
        with open(VEHICLES_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return []


def save_vehicles(vehicles: list[dict[str, Any]]) -> None:
    with open(VEHICLES_FILE, "w", encoding="utf-8") as file:
        json.dump(vehicles, file, ensure_ascii=False, indent=2)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "carrofacil-login-seguro")

    def load_users() -> list[dict]:
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def load_pix_settings() -> dict[str, str]:
        defaults = {
            "pix_key": "",
            "account_number": "",
            "mp_access_token": "",
            "beneficiary_name": "",
        }
        try:
            with open(PIX_SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    return defaults
                return {**defaults, **loaded}
        except FileNotFoundError:
            return defaults

    def save_pix_settings(settings: dict[str, str]) -> None:
        payload = {
            "pix_key": (settings.get("pix_key") or "").strip(),
            "account_number": (settings.get("account_number") or "").strip(),
            "mp_access_token": (settings.get("mp_access_token") or "").strip(),
            "beneficiary_name": (settings.get("beneficiary_name") or "").strip(),
        }
        with open(PIX_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


    def save_users(users: list[dict]) -> None:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

    def load_sellers() -> list[dict]:
        try:
            with open(SELLERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_sellers(sellers: list[dict]) -> None:
        with open(SELLERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sellers, f, ensure_ascii=False, indent=2)

    def load_commissions() -> list[dict]:
        try:
            with open(COMMISSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_commissions(commissions: list[dict]) -> None:
        with open(COMMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(commissions, f, ensure_ascii=False, indent=2)


    def load_seller_goals() -> list[dict]:
        try:
            with open(GOALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_seller_goals(goals: list[dict]) -> None:
        with open(GOALS_FILE, "w", encoding="utf-8") as f:
            json.dump(goals, f, ensure_ascii=False, indent=2)

    def get_current_seller() -> dict:
        logged_user = session.get("logged_user")
        if logged_user:
            users = load_users()
            for u in users:
                if u.get("username") == logged_user or u.get("email") == logged_user:
                    return u
        users = load_users()
        env_user = os.environ.get("SELLER_USERNAME")
        if env_user:
            for u in users:
                if u.get("username") == env_user or u.get("email") == env_user:
                    return u
        return users[0] if users else {"username": "vendedor", "name": "Vendedor"}

    @app.context_processor
    def inject_user():
        return {
            "user": get_current_seller(),
            "sellers": load_users(),
            "is_manager": bool(get_current_seller().get("is_manager")),
            "pix_settings": load_pix_settings(),
        }

    def create_mercado_pago_pix_payment(
        *, amount: float, description: str, payer_email: str, payer_name: str, payer_cpf: str, external_reference: str
    ) -> dict[str, Any]:
        clean_cpf = _clean_digits(payer_cpf)
        if len(clean_cpf) != 11:
            return {"status": "error", "message": "CPF do cliente inválido para pagamento Pix."}

        if "@" not in payer_email:
            return {"status": "error", "message": "Informe um e-mail válido do cliente para pagamento Pix."}

        settings = load_pix_settings()
        access_token = (settings.get("mp_access_token") or "").strip()
        if not access_token:
            return {"status": "error", "message": "Token do Mercado Pago não configurado. Atualize em Gerencial > Configuração Pix."}

        payload = {
            "transaction_amount": float(round(amount, 2)),
            "description": description,
            "payment_method_id": "pix",
            "external_reference": external_reference,
            "payer": {
                "email": payer_email,
                "first_name": payer_name or "Cliente",
                "identification": {
                    "type": "CPF",
                    "number": clean_cpf,
                },
            },
        }

        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            "https://api.mercadopago.com/v1/payments",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "X-Idempotency-Key": str(uuid4()),
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=12) as response:
                mp_data = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            return {"status": "error", "message": f"Mercado Pago retornou erro: {raw or exc.reason}"}
        except Exception as exc:
            return {"status": "error", "message": f"Falha ao gerar pagamento Pix no Mercado Pago: {exc}"}

        tx_data = (mp_data.get("point_of_interaction") or {}).get("transaction_data") or {}
        return {
            "status": mp_data.get("status") or "pending",
            "payment_id": mp_data.get("id"),
            "qr_code": tx_data.get("qr_code", ""),
            "qr_code_base64": tx_data.get("qr_code_base64", ""),
            "ticket_url": tx_data.get("ticket_url", ""),
            "message": "Pagamento Pix criado com sucesso no Mercado Pago.",
        }

    def get_mercado_pago_payment_status(payment_id: Any) -> dict[str, Any]:
        settings = load_pix_settings()
        access_token = (settings.get("mp_access_token") or "").strip()
        if not access_token:
            return {"status": "error", "message": "Token do Mercado Pago não configurado."}
        if not payment_id:
            return {"status": "error", "message": "ID do pagamento inválido."}

        req = urlrequest.Request(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urlrequest.urlopen(req, timeout=12) as response:
                mp_data = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            return {"status": "error", "message": f"Mercado Pago retornou erro: {raw or exc.reason}"}
        except Exception as exc:
            return {"status": "error", "message": f"Falha ao consultar pagamento Pix: {exc}"}

        tx_data = (mp_data.get("point_of_interaction") or {}).get("transaction_data") or {}
        return {
            "status": mp_data.get("status") or "pending",
            "payment_id": mp_data.get("id"),
            "qr_code": tx_data.get("qr_code", ""),
            "qr_code_base64": tx_data.get("qr_code_base64", ""),
            "ticket_url": tx_data.get("ticket_url", ""),
            "message": "Status Pix consultado com sucesso.",
        }

    def is_authenticated() -> bool:
        return bool(session.get("logged_user"))

    def authenticate_user(username: str, password: str) -> dict | None:
        normalized = (username or "").strip().lower()
        secret = (password or "").strip()
        if not normalized or not secret:
            return None

        for user in load_users():
            by_username = (user.get("username") or "").strip().lower() == normalized
            if by_username and str(user.get("password") or "") == secret:
                return user
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if is_authenticated():
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            user = authenticate_user(username, password)
            if user:
                session["logged_user"] = user.get("username")
                return redirect(url_for("index"))

            return render_template(
                "login.html",
                error="Usuário ou senha inválidos.",
                username=username,
            )

        return render_template("login.html", error=None, username="")

    @app.route("/logout", methods=["GET"])
    def logout():
        session.pop("logged_user", None)
        return redirect(url_for("login"))

    def require_authentication():
        if not is_authenticated():
            return redirect(url_for("login"))
        return None


    def require_manager_access():
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        if not bool(get_current_seller().get("is_manager")):
            return redirect(url_for("index"))
        return None


    def parse_sale_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def parse_filter_date(value: str, end_of_day: bool = False) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                return dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            return None

    def normalize_text(value: Any) -> str:
        return str(value or "").strip().lower()

    def build_seller_month_goal(user: dict) -> dict:
        seller_key = normalize_text(user.get("name") or user.get("username"))
        now = datetime.now()
        sold_so_far = 0

        for sale in load_sales():
            if normalize_text(sale.get("vendedor")) != seller_key:
                continue
            sale_dt = parse_sale_datetime(sale.get("created_at", ""))
            if sale_dt and sale_dt.year == now.year and sale_dt.month == now.month:
                sold_so_far += 1

        goals_by_seller = {
            normalize_text(goal.get("seller_name")): goal
            for goal in load_seller_goals()
            if normalize_text(goal.get("seller_name"))
        }
        seller_goal = goals_by_seller.get(seller_key) or {}
        target_total = int(seller_goal.get("target", 0) or 0)

        return {
            "month_label": now.strftime("%m/%Y"),
            "sold_so_far": sold_so_far,
            "target_total": target_total,
        }

    def build_reports(start_date: str, end_date: str) -> dict:
        dt_start = parse_filter_date((start_date or "").strip())
        dt_end = parse_filter_date((end_date or "").strip(), end_of_day=True)

        sales = load_sales()
        vehicles = load_vehicles()
        goals = load_seller_goals()

        filtered_sales: list[dict] = []
        for sale in sales:
            sdt = parse_sale_datetime(sale.get("created_at", ""))
            if dt_start and (sdt is None or sdt < dt_start):
                continue
            if dt_end and (sdt is None or sdt > dt_end):
                continue
            filtered_sales.append(sale)

        total_sales_value = sum(float(s.get("final_price") or 0) for s in filtered_sales)

        sold_total = len([v for v in vehicles if v.get("status") == "vendido"])
        current_registered = len(vehicles)
        available_total = len([v for v in vehicles if v.get("status") == "disponivel"])

        goals_by_seller = {(g.get("seller_name") or "").strip().lower(): g for g in goals if g.get("seller_name")}
        sales_count_by_seller: dict[str, int] = {}
        all_sellers: set[str] = set()

        for sale in filtered_sales:
            seller = (sale.get("vendedor") or "Sem vendedor").strip()
            sales_count_by_seller[seller] = sales_count_by_seller.get(seller, 0) + 1
            all_sellers.add(seller)

        for user in load_users():
            name = (user.get("name") or user.get("username") or "").strip()
            if name:
                all_sellers.add(name)

        for seller in load_sellers():
            name = (seller.get("name") or "").strip()
            if name:
                all_sellers.add(name)

        for goal in goals:
            name = (goal.get("seller_name") or "").strip()
            if name:
                all_sellers.add(name)

        seller_goals_report = []
        for seller_name in sorted(all_sellers):
            sold_qty = sales_count_by_seller.get(seller_name, 0)
            goal = goals_by_seller.get(seller_name.lower())
            target = int(goal.get("target", 0)) if goal else 0
            progress = (sold_qty / target * 100) if target > 0 else 0
            seller_goals_report.append({
                "seller_name": seller_name,
                "sold_qty": sold_qty,
                "target": target,
                "progress": progress,
            })

        return {
            "start_date": (start_date or "").strip(),
            "end_date": (end_date or "").strip(),
            "sales_qty": len(filtered_sales),
            "sales_total_value": total_sales_value,
            "vehicles_sold_total": sold_total,
            "vehicles_registered_total": current_registered,
            "vehicles_available_total": available_total,
            "seller_goals_report": seller_goals_report,
        }

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

    def build_xlsx_bytes(reports: dict) -> bytes:
        from io import BytesIO
        from zipfile import ZIP_DEFLATED, ZipFile

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

        rows_summary = [
            ["Métrica", "Valor"],
            ["Data inicial", reports.get("start_date") or "-"],
            ["Data final", reports.get("end_date") or "-"],
            ["Total de vendas (R$)", float(reports.get("sales_total_value") or 0)],
            ["Quantidade de vendas", int(reports.get("sales_qty") or 0)],
            ["Carros vendidos", int(reports.get("vehicles_sold_total") or 0)],
            ["Carros cadastrados atuais", int(reports.get("vehicles_registered_total") or 0)],
            ["Carros disponíveis", int(reports.get("vehicles_available_total") or 0)],
        ]

        rows_goals = [["Vendedor", "Vendas no período", "Meta", "Atingimento (%)"]]
        for item in reports.get("seller_goals_report", []):
            rows_goals.append([
                item.get("seller_name") or "",
                int(item.get("sold_qty") or 0),
                int(item.get("target") or 0),
                round(float(item.get("progress") or 0), 2),
            ])

        sheet1 = make_sheet(rows_summary)
        sheet2 = make_sheet(rows_goals)

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

        workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Resumo" sheetId="1" r:id="rId1"/>
    <sheet name="Metas" sheetId="2" r:id="rId2"/>
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

    @app.route("/gerencial/relatorios/export/pdf", methods=["GET"])
    def export_report_pdf():
        manager_redirect = require_manager_access()
        if manager_redirect:
            return manager_redirect

        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()
        reports = build_reports(start_date, end_date)

        lines = [
            "Relatorio Gerencial de Vendas",
            f"Data inicial: {reports.get('start_date') or '-'}",
            f"Data final: {reports.get('end_date') or '-'}",
            "",
            f"Total de vendas (R$): {reports.get('sales_total_value', 0):.2f}",
            f"Quantidade de vendas: {reports.get('sales_qty', 0)}",
            f"Carros vendidos: {reports.get('vehicles_sold_total', 0)}",
            f"Carros cadastrados atuais: {reports.get('vehicles_registered_total', 0)}",
            f"Carros disponiveis: {reports.get('vehicles_available_total', 0)}",
            "",
            "Meta por vendedor:",
        ]

        for item in reports.get("seller_goals_report", []):
            target = item.get("target", 0)
            target_text = str(target) if target else "-"
            progress_text = f"{item.get('progress', 0):.1f}%" if target else "-"
            lines.append(
                f"- {item.get('seller_name')}: vendas={item.get('sold_qty', 0)}, meta={target_text}, atingimento={progress_text}"
            )

        payload = build_simple_pdf(lines)
        return app.response_class(
            payload,
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename=relatorio-gerencial.pdf"},
        )

    @app.route("/gerencial/relatorios/export/xlsx", methods=["GET"])
    def export_report_xlsx():
        manager_redirect = require_manager_access()
        if manager_redirect:
            return manager_redirect

        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()
        reports = build_reports(start_date, end_date)
        payload = build_xlsx_bytes(reports)

        return app.response_class(
            payload,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=relatorio-gerencial.xlsx"},
        )

    @app.route("/gerencial", methods=["GET", "POST"])
    def gerencial():
        manager_redirect = require_manager_access()
        if manager_redirect:
            return manager_redirect

        error = None
        success = None
        active_tab = request.args.get("tab", "gestao")

        if request.method == "POST":
            action = request.form.get("action", "").strip()
            active_tab = request.form.get("active_tab", active_tab)

            if action == "seller":
                seller_name = request.form.get("seller_name", "").strip()
                seller_phone = request.form.get("seller_phone", "").strip()
                if not seller_name:
                    error = "Informe o nome do vendedor."
                else:
                    sellers = load_sellers()
                    sellers.append({
                        "id": str(uuid4())[:8],
                        "name": seller_name,
                        "phone": seller_phone,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    save_sellers(sellers)
                    success = "Vendedor cadastrado com sucesso."

            elif action == "commission":
                seller_name = request.form.get("commission_seller", "").strip()
                percent = request.form.get("commission_percent", "").strip().replace(",", ".")
                if not seller_name or not percent:
                    error = "Informe vendedor e percentual da comissão."
                else:
                    try:
                        percent_value = float(percent)
                    except ValueError:
                        percent_value = -1
                    if percent_value < 0:
                        error = "Percentual de comissão inválido."
                    else:
                        commissions = load_commissions()
                        commissions.append({
                            "id": str(uuid4())[:8],
                            "seller_name": seller_name,
                            "percent": percent_value,
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        })
                        save_commissions(commissions)
                        success = "Comissão cadastrada com sucesso."

            elif action == "access":
                username = request.form.get("new_username", "").strip()
                full_name = request.form.get("new_name", "").strip()
                password = request.form.get("new_password", "").strip()
                is_manager = request.form.get("allow_manager") == "yes"

                if not username or not password:
                    error = "Informe usuário e senha para criar o acesso."
                else:
                    users = load_users()
                    exists = any((u.get("username") or "").lower() == username.lower() for u in users)
                    if exists:
                        error = "Este usuário já existe."
                    else:
                        users.append({
                            "id": len(users) + 1,
                            "username": username,
                            "name": full_name or username,
                            "password": password,
                            "is_manager": is_manager,
                        })
                        save_users(users)
                        success = "Acesso criado com sucesso."

            elif action == "goal":
                seller_name = request.form.get("goal_seller", "").strip()
                target_raw = request.form.get("goal_target", "").strip()
                if not seller_name or not target_raw:
                    error = "Informe vendedor e meta de vendas."
                else:
                    try:
                        target_value = int(float(target_raw))
                    except ValueError:
                        target_value = -1
                    if target_value < 0:
                        error = "Meta de vendas inválida."
                    else:
                        goals = load_seller_goals()
                        existing = next((g for g in goals if (g.get("seller_name") or "").lower() == seller_name.lower()), None)
                        if existing:
                            existing["target"] = target_value
                            existing["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            goals.append({
                                "id": str(uuid4())[:8],
                                "seller_name": seller_name,
                                "target": target_value,
                                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            })
                        save_seller_goals(goals)
                        success = "Meta de vendedor salva com sucesso."
            elif action == "pix_settings":
                pix_key = request.form.get("pix_key", "").strip()
                account_number = request.form.get("account_number", "").strip()
                mp_access_token = request.form.get("mp_access_token", "").strip()
                beneficiary_name = request.form.get("beneficiary_name", "").strip()

                if not pix_key or not account_number:
                    error = "Informe chave Pix e número da conta para salvar a configuração."
                else:
                    save_pix_settings({
                        "pix_key": pix_key,
                        "account_number": account_number,
                        "mp_access_token": mp_access_token,
                        "beneficiary_name": beneficiary_name,
                    })
                    success = "Configuração de Pix atualizada com sucesso."
            else:
                error = "Ação inválida."

        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()
        reports = build_reports(start_date, end_date)

        return render_template(
            "gerencial.html",
            sellers_registry=load_sellers(),
            commissions_registry=load_commissions(),
            users_registry=load_users(),
            goals_registry=load_seller_goals(),
            reports=reports,
            active_tab=active_tab,
            error=error,
            success=success,
            pix_registry=load_pix_settings(),
        )

    @app.route("/", methods=["GET"])
    def index():
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        user = get_current_seller()
        is_manager = bool(user.get("is_manager"))
        seller_goal_dashboard = build_seller_month_goal(user) if not is_manager else None
        vehicles = load_vehicles()
        available = [v for v in vehicles if v["status"] == "disponivel"]
        sold = [v for v in vehicles if v["status"] == "vendido"]
        return render_template(
            "index.html",
            available_count=len(available),
            sold_count=len(sold),
            total_count=len(vehicles),
            recent_vehicles=list(reversed(vehicles[-5:])),
            seller_goal_dashboard=seller_goal_dashboard,
        )

    @app.route("/cadastro", methods=["GET", "POST"])
    def cadastro():
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        if request.method == "POST":
            form_data = {
                "marca": request.form.get("marca", "").strip(),
                "modelo": request.form.get("modelo", "").strip(),
                "cor": request.form.get("cor", "").strip(),
                "ano": request.form.get("ano", "").strip(),
                "renavam": request.form.get("renavam", "").strip(),
                "placa": request.form.get("placa", "").strip().upper(),
                "ipva_vencimento": request.form.get("ipva_vencimento", "").strip(),
                "preco": request.form.get("preco", "").strip(),
                "km": request.form.get("km", "").strip(),
            }

            # normalizar preço para duas casas decimais se informado
            if form_data.get("preco"):
                try:
                    form_data["preco"] = f"{_to_float_price(form_data.get('preco', '0')):.2f}"
                except Exception:
                    form_data["preco"] = form_data.get("preco")

            missing = [label for key, label in REQUIRED_FIELDS.items() if not form_data.get(key)]
            if missing:
                return render_template(
                    "cadastro.html",
                    created=False,
                    error=f"Preencha os campos obrigatórios: {', '.join(missing)}.",
                    form_data=form_data,
                )

            vehicle = {"id": str(uuid4())[:8], **form_data, "status": "disponivel"}
            vehicles = load_vehicles()
            vehicles.append(vehicle)
            save_vehicles(vehicles)
            return redirect(url_for("cadastro", created="1"))

        created = request.args.get("created") == "1"
        return render_template("cadastro.html", created=created, error=None, form_data={})

    @app.route("/vendas", methods=["GET"])
    def vendas():
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        q = (request.args.get("q") or "").strip()
        vehicles = load_vehicles()
        # attach vendedor info from latest sales when available
        sales = load_sales()
        latest_by_vehicle: dict[str, dict] = {}
        for s in sales:
            vid = s.get("vehicle_id")
            if not vid:
                continue
            # keep latest occurrence (sales appended chronologically)
            latest_by_vehicle[vid] = s
        if q:
            ql = q.lower()
            def matches(v: dict) -> bool:
                text = " ".join([v.get(k, "") for k in ("marca", "modelo", "placa", "renavam")])
                return ql in text.lower()
            vehicles = [v for v in vehicles if matches(v)]
            # annotate vehicles with vendedor and sale date if sold
        for v in vehicles:
            if v.get("status") == "vendido":
                sale = latest_by_vehicle.get(v.get("id"))
                if sale:
                    v["vendedor"] = sale.get("vendedor")
                    v["venda_data"] = sale.get("created_at")
                else:
                    v["vendedor"] = None
                    v["venda_data"] = None
        return render_template("vendas.html", vehicles=vehicles, q=q)

    def save_sale(sale: dict) -> None:
        sales = []
        try:
            with open(SALES_FILE, "r", encoding="utf-8") as f:
                sales = json.load(f)
        except FileNotFoundError:
            sales = []
        sales.append(sale)
        with open(SALES_FILE, "w", encoding="utf-8") as f:
            json.dump(sales, f, ensure_ascii=False, indent=2)

    def load_sales() -> list[dict]:
        try:
            with open(SALES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def _to_float_price(value: str) -> float:
        try:
            return float(value.replace("R$", "").replace(" ", "").replace(".", "").replace(",", "."))
        except Exception:
            try:
                return float(value)
            except Exception:
                return 0.0

    def _clean_digits(s: str) -> str:
        return ''.join(ch for ch in (s or '') if ch.isdigit())

    def validate_cpf(cpf: str) -> bool:
        cpf = _clean_digits(cpf)
        if len(cpf) != 11:
            return False
        if cpf == cpf[0] * 11:
            return False
        def calc(digs: str) -> int:
            s = 0
            for i, ch in enumerate(digs):
                s += int(ch) * (len(digs) + 1 - i)
            r = 11 - (s % 11)
            return 0 if r > 9 else r
        d1 = calc(cpf[:9])
        d2 = calc(cpf[:10])
        return d1 == int(cpf[9]) and d2 == int(cpf[10])

    @app.route("/vendas/<vehicle_id>/vender", methods=["GET", "POST"])
    def vender(vehicle_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        vehicles = load_vehicles()
        vehicle = next((v for v in vehicles if v["id"] == vehicle_id), None)
        if vehicle is None:
            return redirect(url_for("vendas"))

        # garantir placa em maiúsculas para exibição e processamento
        vehicle["placa"] = (vehicle.get("placa") or "").upper()

        if request.method == "POST":
            cliente_nome = request.form.get("cliente_nome", "").strip()
            cliente_cpf = request.form.get("cliente_cpf", "").strip()
            cliente_cnh = request.form.get("cliente_cnh", "").strip()
            cliente_endereco = request.form.get("cliente_endereco", "").strip()
            forma_pagamento = request.form.get("forma_pagamento", "")
            cliente_email = request.form.get("cliente_email", "").strip()
            houve_negociacao = request.form.get("houve_negociacao", "no") == "yes"
            negociacao_desc = request.form.get("negociacao_desc", "").strip()
            negociacao_valor = request.form.get("negociacao_valor", "0").strip()

            # validar CPF no servidor
            form_data = request.form
            if not validate_cpf(cliente_cpf):
                return render_template("vender.html", vehicle=vehicle, error="CPF inválido.", form_data=form_data)

            base_price = _to_float_price(vehicle.get("preco", "0"))
            neg_val = _to_float_price(negociacao_valor) if houve_negociacao else 0.0
            final_price = max(0.0, base_price - neg_val)

            sale = {
                "id": str(uuid4())[:8],
                "vehicle_id": vehicle_id,
                "vehicle": {**vehicle, "placa": (vehicle.get("placa") or "").upper()},
                "vendedor": (request.form.get("vendedor_name") or get_current_seller().get("name") or get_current_seller().get("username")),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cliente_nome": cliente_nome,
                "cliente_cpf": cliente_cpf,
                "cliente_cnh": cliente_cnh,
                "cliente_endereco": cliente_endereco,
                "forma_pagamento": forma_pagamento,
                "cliente_email": cliente_email,
                "houve_negociacao": houve_negociacao,
                "negociacao_desc": negociacao_desc,
                "negociacao_valor": neg_val,
                "base_price": base_price,
                "final_price": final_price,
            }

            if forma_pagamento == "pix_mercado_pago":
                pix_result = create_mercado_pago_pix_payment(
                    amount=final_price,
                    description=f"Compra do veículo {vehicle.get('marca', '')} {vehicle.get('modelo', '')}".strip(),
                    payer_email=cliente_email,
                    payer_name=cliente_nome,
                    payer_cpf=cliente_cpf,
                    external_reference=sale["id"],
                )
                if pix_result.get("status") == "error":
                    return render_template(
                        "vender.html",
                        vehicle=vehicle,
                        error=pix_result.get("message") or "Falha ao gerar Pix no Mercado Pago.",
                        form_data=request.form,
                    )
                sale["pix_payment"] = pix_result

            # update vehicle status, price and placa (maiúscula)
            for v in vehicles:
                if v["id"] == vehicle_id:
                    v["status"] = "vendido"
                    v["preco"] = f"{final_price:.2f}"
                    v["placa"] = (v.get("placa") or "").upper()
                    break
            save_vehicles(vehicles)

            save_sale(sale)
            return redirect(url_for("nota", vehicle_id=vehicle_id))

        # GET -> show form
        return render_template("vender.html", vehicle=vehicle)

    @app.route("/vendas/<vehicle_id>/nota", methods=["GET"])
    def nota(vehicle_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        # find latest sale for this vehicle
        sales = load_sales()
        sale = None
        for s in reversed(sales):
            if s.get("vehicle_id") == vehicle_id:
                sale = s
                break
        if sale is None:
            return redirect(url_for("vendas"))
        return render_template("nota.html", sale=sale)

    @app.route("/vendas/<vehicle_id>/pix/atualizar", methods=["POST"])
    def atualizar_status_pix(vehicle_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect

        sales = load_sales()
        sale_index = None
        for i in range(len(sales) - 1, -1, -1):
            if sales[i].get("vehicle_id") == vehicle_id:
                sale_index = i
                break

        if sale_index is None:
            return redirect(url_for("vendas"))

        sale = sales[sale_index]
        pix_payment = sale.get("pix_payment") or {}
        payment_id = pix_payment.get("payment_id")
        if not payment_id:
            return redirect(url_for("nota", vehicle_id=vehicle_id))

        sale["pix_payment"] = get_mercado_pago_payment_status(payment_id)
        sales[sale_index] = sale
        with open(SALES_FILE, "w", encoding="utf-8") as f:
            json.dump(sales, f, ensure_ascii=False, indent=2)

        return redirect(url_for("nota", vehicle_id=vehicle_id))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
