from __future__ import annotations

import json
import os
from typing import Any
from datetime import datetime
from uuid import uuid4

from flask import Flask, redirect, render_template, request, session, url_for

from utils.report_exports import build_simple_pdf, build_xlsx_bytes, report_lines_for_type

DATA_DIR = os.path.dirname(__file__)
VEHICLES_FILE = os.path.join(DATA_DIR, "vehicles.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SELLERS_FILE = os.path.join(DATA_DIR, "sellers.json")
COMMISSIONS_FILE = os.path.join(DATA_DIR, "commissions.json")
GOALS_FILE = os.path.join(DATA_DIR, "seller_goals.json")

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
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "erp-veiculos-login-seguro")

    def load_users() -> list[dict]:
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []


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
        return {"user": get_current_seller(), "sellers": load_users(), "is_manager": bool(get_current_seller().get("is_manager"))}

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

    def build_reports(start_date: str, end_date: str, car_brand: str = "", car_start_date: str = "", car_end_date: str = "") -> dict:
        dt_start = parse_filter_date((start_date or "").strip())
        dt_end = parse_filter_date((end_date or "").strip(), end_of_day=True)

        car_brand_norm = (car_brand or "").strip().lower()
        car_start = (car_start_date or start_date or "").strip()
        car_end = (car_end_date or end_date or "").strip()
        car_dt_start = parse_filter_date(car_start)
        car_dt_end = parse_filter_date(car_end, end_of_day=True)

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

        filtered_car_sales: list[dict] = []
        for sale in sales:
            sdt = parse_sale_datetime(sale.get("created_at", ""))
            if car_dt_start and (sdt is None or sdt < car_dt_start):
                continue
            if car_dt_end and (sdt is None or sdt > car_dt_end):
                continue
            sale_brand = ((sale.get("vehicle") or {}).get("marca") or "").strip().lower()
            if car_brand_norm and sale_brand != car_brand_norm:
                continue
            filtered_car_sales.append(sale)

        sold_total = len(filtered_car_sales)
        if car_brand_norm:
            current_registered = len([v for v in vehicles if (v.get("marca") or "").strip().lower() == car_brand_norm])
            available_total = len([v for v in vehicles if (v.get("status") == "disponivel" and (v.get("marca") or "").strip().lower() == car_brand_norm)])
        else:
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
            "car_brand": (car_brand or "").strip(),
            "car_start_date": car_start,
            "car_end_date": car_end,
        }

    @app.route("/gerencial/relatorios/export/pdf", methods=["GET"])
    def export_report_pdf():
        manager_redirect = require_manager_access()
        if manager_redirect:
            return manager_redirect

        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()
        car_brand = (request.args.get("car_brand") or "").strip()
        car_start_date = (request.args.get("car_start_date") or "").strip()
        car_end_date = (request.args.get("car_end_date") or "").strip()
        report_type = (request.args.get("report_type") or "resumo").strip().lower()
        reports = build_reports(start_date, end_date, car_brand, car_start_date, car_end_date)
        lines = report_lines_for_type(report_type, reports)

        payload = build_simple_pdf(lines)
        filename = f"relatorio-{report_type}.pdf"
        return app.response_class(
            payload,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/gerencial/relatorios/export/xlsx", methods=["GET"])
    def export_report_xlsx():
        manager_redirect = require_manager_access()
        if manager_redirect:
            return manager_redirect

        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()
        car_brand = (request.args.get("car_brand") or "").strip()
        car_start_date = (request.args.get("car_start_date") or "").strip()
        car_end_date = (request.args.get("car_end_date") or "").strip()
        report_type = (request.args.get("report_type") or "resumo").strip().lower()
        reports = build_reports(start_date, end_date, car_brand, car_start_date, car_end_date)
        payload = build_xlsx_bytes(reports, report_type)

        filename = f"relatorio-{report_type}.xlsx"
        return app.response_class(
            payload,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
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
            else:
                error = "Ação inválida."

        start_date = (request.args.get("start_date") or "").strip()
        end_date = (request.args.get("end_date") or "").strip()
        car_brand = (request.args.get("car_brand") or "").strip()
        car_start_date = (request.args.get("car_start_date") or "").strip()
        car_end_date = (request.args.get("car_end_date") or "").strip()
        reports = build_reports(start_date, end_date, car_brand, car_start_date, car_end_date)

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
        )

    @app.route("/", methods=["GET"])
    def index():
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect
        vehicles = load_vehicles()
        available = [v for v in vehicles if v["status"] == "disponivel"]
        sold = [v for v in vehicles if v["status"] == "vendido"]
        return render_template(
            "index.html",
            available_count=len(available),
            sold_count=len(sold),
            total_count=len(vehicles),
            recent_vehicles=list(reversed(vehicles[-5:])),
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

            # update vehicle status, price and placa (maiúscula)
            for v in vehicles:
                if v["id"] == vehicle_id:
                    v["status"] = "vendido"
                    v["preco"] = f"{final_price:.2f}"
                    v["placa"] = (v.get("placa") or "").upper()
                    break
            save_vehicles(vehicles)

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
                "houve_negociacao": houve_negociacao,
                "negociacao_desc": negociacao_desc,
                "negociacao_valor": neg_val,
                "base_price": base_price,
                "final_price": final_price,
            }
            save_sale(sale)
            return redirect(url_for("vendas"))

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

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
