from __future__ import annotations

import json
import os
import sqlite3
from typing import Any
from datetime import datetime
from uuid import uuid4
import xml.etree.ElementTree as ET
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from flask import Flask, redirect, render_template, request, send_file, session, url_for

DATA_DIR = os.path.dirname(__file__)
VEHICLES_FILE = os.path.join(DATA_DIR, "vehicles.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")
RENTALS_FILE = os.path.join(DATA_DIR, "rentals.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SELLERS_FILE = os.path.join(DATA_DIR, "sellers.json")
COMMISSIONS_FILE = os.path.join(DATA_DIR, "commissions.json")
GOALS_FILE = os.path.join(DATA_DIR, "seller_goals.json")
DB_DIR = os.path.join(DATA_DIR, "database")
DB_FILE = os.path.join(DB_DIR, "ecommerce_veiculos.db")
DB_SCHEMA_FILE = os.path.join(DB_DIR, "schema.sql")
NOTAS_XML_DIR = os.path.join(DB_DIR, "notas_xml")

REQUIRED_FIELDS = {
    "marca": "Marca",
    "modelo": "Modelo",
    "ano": "Ano",
    "renavam": "Renavam",
    "placa": "Placa",
    "ipva_vencimento": "Data de vencimento do IPVA",
}

ph = PasswordHasher()

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        ph.verify(hashed, password)
        return True
    except VerifyMismatchError:
        return False

def _read_json_array(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return []


def _to_db_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        return 0.0

    text = "".join(ch for ch in text if ch.isdigit() or ch in {".", ",", "-"})
    if not text or text in {"-", ".", ",", "-.", "-,"}:
        return 0.0

    negative = text.startswith("-")
    if negative:
        text = text[1:]

    has_comma = "," in text
    has_dot = "." in text

    if has_comma and has_dot:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        parts = text.split(",")
        if len(parts) > 2:
            text = "".join(parts[:-1]) + "." + parts[-1]
        else:
            text = text.replace(",", ".")
    elif has_dot:
        parts = text.split(".")
        if len(parts) > 2:
            last = parts[-1]
            if len(last) <= 2:
                text = "".join(parts[:-1]) + "." + last
            else:
                text = "".join(parts)
        else:
            integer_part, decimal_part = parts
            if decimal_part and len(decimal_part) == 3 and integer_part.isdigit():
                text = integer_part + decimal_part

    if negative:
        text = "-" + text

    try:
        return float(text)
    except ValueError:
        return 0.0


def _to_db_bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE)
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def ensure_database_ready() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    os.makedirs(NOTAS_XML_DIR, exist_ok=True)

    if not os.path.exists(DB_SCHEMA_FILE):
        return

    with get_db_connection() as connection:
        schema_sql = ""
        with open(DB_SCHEMA_FILE, "r", encoding="utf-8") as schema_file:
            schema_sql = schema_file.read()
        connection.executescript(schema_sql)

        sales_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sales)").fetchall()
        }
        if "nota_xml_path" not in sales_columns:
            connection.execute("ALTER TABLE sales ADD COLUMN nota_xml_path TEXT")

        vehicles_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(vehicles)").fetchall()
        }
        if "diaria_aluguel" not in vehicles_columns:
            connection.execute("ALTER TABLE vehicles ADD COLUMN diaria_aluguel REAL NOT NULL DEFAULT 0")

        connection.commit()


def sync_users_to_db(users: list[dict[str, Any]]) -> None:
    if not users:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for user in users:
            username = str(user.get("username") or "").strip()
            if not username:
                continue

            user_id: int | None = None
            try:
                user_id = int(user.get("id"))
            except (TypeError, ValueError):
                user_id = None

            raw_password = str(user.get("password") or "").strip()
            if raw_password.startswith("$argon2"):
                stored_password = raw_password
            else:
                stored_password = hash_password(raw_password) if raw_password else ""
            connection.execute(
                """
                INSERT INTO users (id, username, name, email, password, is_manager)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    password = excluded.password,
                    is_manager = excluded.is_manager
                """,
                (
                    user_id,
                    username,
                    str(user.get("name") or username).strip(),
                    str(user.get("email") or "").strip(),
                    stored_password,
                    _to_db_bool_int(user.get("is_manager")),
                ),
            )
        connection.commit()


def sync_sellers_to_db(sellers: list[dict[str, Any]]) -> None:
    if not sellers:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for seller in sellers:
            seller_id = str(seller.get("id") or "").strip()
            if not seller_id:
                continue

            connection.execute(
                """
                INSERT INTO sellers (id, name, phone, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    phone = excluded.phone
                """,
                (
                    seller_id,
                    str(seller.get("name") or "").strip(),
                    str(seller.get("phone") or "").strip(),
                    str(seller.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).strip(),
                ),
            )
        connection.commit()


def sync_commissions_to_db(commissions: list[dict[str, Any]]) -> None:
    if not commissions:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for commission in commissions:
            commission_id = str(commission.get("id") or "").strip()
            if not commission_id:
                continue

            connection.execute(
                """
                INSERT INTO commissions (id, seller_name, percent, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    seller_name = excluded.seller_name,
                    percent = excluded.percent
                """,
                (
                    commission_id,
                    str(commission.get("seller_name") or "").strip(),
                    _to_db_float(commission.get("percent")),
                    str(commission.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).strip(),
                ),
            )
        connection.commit()


def sync_seller_goals_to_db(goals: list[dict[str, Any]]) -> None:
    if not goals:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for goal in goals:
            goal_id = str(goal.get("id") or "").strip()
            if not goal_id:
                continue

            target_value = 0
            try:
                target_value = int(float(goal.get("target") or 0))
            except (TypeError, ValueError):
                target_value = 0

            connection.execute(
                """
                INSERT INTO seller_goals (id, seller_name, target, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    seller_name = excluded.seller_name,
                    target = excluded.target,
                    updated_at = excluded.updated_at
                """,
                (
                    goal_id,
                    str(goal.get("seller_name") or "").strip(),
                    max(0, target_value),
                    str(goal.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).strip(),
                    str(goal.get("updated_at") or "").strip() or None,
                ),
            )
        connection.commit()


def sync_vehicles_to_db(vehicles: list[dict[str, Any]]) -> None:
    if not vehicles:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for vehicle in vehicles:
            vehicle_id = str(vehicle.get("id") or "").strip()
            if not vehicle_id:
                continue

            connection.execute(
                """
                INSERT INTO vehicles (
                    id, marca, modelo, cor, ano, renavam, placa,
                    ipva_vencimento, preco, km, status, diaria_aluguel
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    marca = excluded.marca,
                    modelo = excluded.modelo,
                    cor = excluded.cor,
                    ano = excluded.ano,
                    renavam = excluded.renavam,
                    placa = excluded.placa,
                    ipva_vencimento = excluded.ipva_vencimento,
                    preco = excluded.preco,
                    km = excluded.km,
                    status = excluded.status,
                    diaria_aluguel = excluded.diaria_aluguel
                """,
                (
                    vehicle_id,
                    str(vehicle.get("marca") or "").strip(),
                    str(vehicle.get("modelo") or "").strip(),
                    str(vehicle.get("cor") or "").strip() or None,
                    str(vehicle.get("ano") or "").strip(),
                    str(vehicle.get("renavam") or "").strip(),
                    str(vehicle.get("placa") or "").strip().upper(),
                    str(vehicle.get("ipva_vencimento") or "").strip(),
                    _to_db_float(vehicle.get("preco")),
                    str(vehicle.get("km") or "").strip() or None,
                    str(vehicle.get("status") or "disponivel").strip(),
                    _to_db_float(vehicle.get("diaria_aluguel")),
                ),
            )
        connection.commit()


def create_nota_xml(sale: dict[str, Any]) -> str:
    ensure_database_ready()

    sale_id = str(sale.get("id") or "").strip()
    if not sale_id:
        sale_id = str(uuid4())[:8]

    xml_path = os.path.join(NOTAS_XML_DIR, f"nota-{sale_id}.xml")
    vehicle = sale.get("vehicle") if isinstance(sale.get("vehicle"), dict) else {}

    root = ET.Element("nota_venda")
    ET.SubElement(root, "id").text = sale_id
    ET.SubElement(root, "created_at").text = str(sale.get("created_at") or "")
    ET.SubElement(root, "vendedor").text = str(sale.get("vendedor") or "")

    cliente = ET.SubElement(root, "cliente")
    ET.SubElement(cliente, "nome").text = str(sale.get("cliente_nome") or "")
    ET.SubElement(cliente, "cpf").text = str(sale.get("cliente_cpf") or "")
    ET.SubElement(cliente, "cnh").text = str(sale.get("cliente_cnh") or "")
    ET.SubElement(cliente, "endereco").text = str(sale.get("cliente_endereco") or "")

    veiculo = ET.SubElement(root, "veiculo")
    ET.SubElement(veiculo, "id").text = str(sale.get("vehicle_id") or vehicle.get("id") or "")
    ET.SubElement(veiculo, "marca").text = str(vehicle.get("marca") or "")
    ET.SubElement(veiculo, "modelo").text = str(vehicle.get("modelo") or "")
    ET.SubElement(veiculo, "ano").text = str(vehicle.get("ano") or "")
    ET.SubElement(veiculo, "placa").text = str(vehicle.get("placa") or "")
    ET.SubElement(veiculo, "renavam").text = str(vehicle.get("renavam") or "")

    pagamento = ET.SubElement(root, "pagamento")
    ET.SubElement(pagamento, "forma").text = str(sale.get("forma_pagamento") or "")
    ET.SubElement(pagamento, "base_price").text = f"{_to_db_float(sale.get('base_price')):.2f}"
    ET.SubElement(pagamento, "final_price").text = f"{_to_db_float(sale.get('final_price')):.2f}"

    negociacao = ET.SubElement(root, "negociacao")
    ET.SubElement(negociacao, "houve").text = "true" if bool(sale.get("houve_negociacao")) else "false"
    ET.SubElement(negociacao, "descricao").text = str(sale.get("negociacao_desc") or "")
    ET.SubElement(negociacao, "valor").text = f"{_to_db_float(sale.get('negociacao_valor')):.2f}"

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return xml_path


def sync_sales_to_db(sales: list[dict[str, Any]]) -> None:
    if not sales:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for sale in sales:
            sale_id = str(sale.get("id") or "").strip()
            vehicle_id = str(sale.get("vehicle_id") or "").strip()
            if not sale_id or not vehicle_id:
                continue

            vehicle_snapshot = sale.get("vehicle") if isinstance(sale.get("vehicle"), dict) else {}

            try:
                connection.execute(
                    """
                    INSERT INTO sales (
                        id, vehicle_id, vehicle_snapshot, vendedor, created_at,
                        cliente_nome, cliente_cpf, cliente_cnh, cliente_endereco,
                        forma_pagamento, houve_negociacao, negociacao_desc,
                        negociacao_valor, base_price, final_price, nota_xml_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        vehicle_id = excluded.vehicle_id,
                        vehicle_snapshot = excluded.vehicle_snapshot,
                        vendedor = excluded.vendedor,
                        created_at = excluded.created_at,
                        cliente_nome = excluded.cliente_nome,
                        cliente_cpf = excluded.cliente_cpf,
                        cliente_cnh = excluded.cliente_cnh,
                        cliente_endereco = excluded.cliente_endereco,
                        forma_pagamento = excluded.forma_pagamento,
                        houve_negociacao = excluded.houve_negociacao,
                        negociacao_desc = excluded.negociacao_desc,
                        negociacao_valor = excluded.negociacao_valor,
                        base_price = excluded.base_price,
                        final_price = excluded.final_price,
                        nota_xml_path = excluded.nota_xml_path
                    """,
                    (
                        sale_id,
                        vehicle_id,
                        json.dumps(vehicle_snapshot, ensure_ascii=False),
                        str(sale.get("vendedor") or "").strip(),
                        str(sale.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).strip(),
                        str(sale.get("cliente_nome") or "").strip(),
                        str(sale.get("cliente_cpf") or "").strip(),
                        str(sale.get("cliente_cnh") or "").strip(),
                        str(sale.get("cliente_endereco") or "").strip(),
                        str(sale.get("forma_pagamento") or "").strip(),
                        _to_db_bool_int(sale.get("houve_negociacao")),
                        str(sale.get("negociacao_desc") or "").strip(),
                        _to_db_float(sale.get("negociacao_valor")),
                        _to_db_float(sale.get("base_price")),
                        _to_db_float(sale.get("final_price")),
                        str(sale.get("nota_xml_path") or "").strip() or None,
                    ),
                )
            except sqlite3.IntegrityError:
                continue

        connection.commit()


def sync_rentals_to_db(rentals: list[dict[str, Any]]) -> None:
    if not rentals:
        return

    ensure_database_ready()
    with get_db_connection() as connection:
        for rental in rentals:
            rental_id = str(rental.get("id") or "").strip()
            vehicle_id = str(rental.get("vehicle_id") or "").strip()
            if not rental_id or not vehicle_id:
                continue

            vehicle_snapshot = rental.get("vehicle") if isinstance(rental.get("vehicle"), dict) else {}

            try:
                connection.execute(
                    """
                    INSERT INTO rentals (
                        id, vehicle_id, vehicle_snapshot, vendedor, created_at,
                        cliente_nome, cliente_cpf, cliente_cnh, cliente_endereco, cliente_telefone,
                        periodo_inicio, periodo_fim, quantidade_diarias, valor_diaria,
                        valor_base, retirada_em_casa, valor_retirada, forma_pagamento,
                        valor_total, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        vehicle_id = excluded.vehicle_id,
                        vehicle_snapshot = excluded.vehicle_snapshot,
                        vendedor = excluded.vendedor,
                        created_at = excluded.created_at,
                        cliente_nome = excluded.cliente_nome,
                        cliente_cpf = excluded.cliente_cpf,
                        cliente_cnh = excluded.cliente_cnh,
                        cliente_endereco = excluded.cliente_endereco,
                        cliente_telefone = excluded.cliente_telefone,
                        periodo_inicio = excluded.periodo_inicio,
                        periodo_fim = excluded.periodo_fim,
                        quantidade_diarias = excluded.quantidade_diarias,
                        valor_diaria = excluded.valor_diaria,
                        valor_base = excluded.valor_base,
                        retirada_em_casa = excluded.retirada_em_casa,
                        valor_retirada = excluded.valor_retirada,
                        forma_pagamento = excluded.forma_pagamento,
                        valor_total = excluded.valor_total,
                        status = excluded.status
                    """,
                    (
                        rental_id,
                        vehicle_id,
                        json.dumps(vehicle_snapshot, ensure_ascii=False),
                        str(rental.get("vendedor") or "").strip(),
                        str(rental.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")).strip(),
                        str(rental.get("cliente_nome") or "").strip(),
                        str(rental.get("cliente_cpf") or "").strip(),
                        str(rental.get("cliente_cnh") or "").strip(),
                        str(rental.get("cliente_endereco") or "").strip(),
                        str(rental.get("cliente_telefone") or "").strip(),
                        str(rental.get("periodo_inicio") or "").strip(),
                        str(rental.get("periodo_fim") or "").strip(),
                        int(float(rental.get("quantidade_diarias") or 0)),
                        _to_db_float(rental.get("valor_diaria")),
                        _to_db_float(rental.get("valor_base")),
                        _to_db_bool_int(rental.get("retirada_em_casa")),
                        _to_db_float(rental.get("valor_retirada")),
                        str(rental.get("forma_pagamento") or "").strip(),
                        _to_db_float(rental.get("valor_total")),
                        str(rental.get("status") or "ativo").strip(),
                    ),
                )
            except sqlite3.IntegrityError:
                continue

        connection.commit()


def sync_all_json_to_db() -> None:
    sync_users_to_db(_read_json_array(USERS_FILE))
    sync_sellers_to_db(_read_json_array(SELLERS_FILE))
    sync_commissions_to_db(_read_json_array(COMMISSIONS_FILE))
    sync_seller_goals_to_db(_read_json_array(GOALS_FILE))
    sync_vehicles_to_db(_read_json_array(VEHICLES_FILE))
    sync_sales_to_db(_read_json_array(SALES_FILE))
    sync_rentals_to_db(_read_json_array(RENTALS_FILE))


def load_vehicles() -> list[dict[str, Any]]:
    return _read_json_array(VEHICLES_FILE)


def save_vehicles(vehicles: list[dict[str, Any]]) -> None:
    with open(VEHICLES_FILE, "w", encoding="utf-8") as file:
        json.dump(vehicles, file, ensure_ascii=False, indent=2)
    sync_vehicles_to_db(vehicles)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "carrofacil-login-seguro")
    ensure_database_ready()
    sync_all_json_to_db()

    def load_users() -> list[dict]:
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []


    def save_users(users: list[dict]) -> None:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        sync_users_to_db(users)

    def load_sellers() -> list[dict]:
        try:
            with open(SELLERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_sellers(sellers: list[dict]) -> None:
        with open(SELLERS_FILE, "w", encoding="utf-8") as f:
            json.dump(sellers, f, ensure_ascii=False, indent=2)
        sync_sellers_to_db(sellers)

    def load_commissions() -> list[dict]:
        try:
            with open(COMMISSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_commissions(commissions: list[dict]) -> None:
        with open(COMMISSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(commissions, f, ensure_ascii=False, indent=2)
        sync_commissions_to_db(commissions)


    def load_seller_goals() -> list[dict]:
        try:
            with open(GOALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_seller_goals(goals: list[dict]) -> None:
        with open(GOALS_FILE, "w", encoding="utf-8") as f:
            json.dump(goals, f, ensure_ascii=False, indent=2)
        sync_seller_goals_to_db(goals)

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
            stored_hash = str(user.get("password") or "")
            by_username = (user.get("username") or "").strip().lower() == normalized
            if not by_username:
                continue
            if stored_hash.startswith("$argon2"):
                if verify_password(secret, stored_hash):
                    return user
            else:
                if stored_hash == secret:
                    user["password"] = hash_password(secret)
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

            elif action == "rental_price":
                vehicle_id = request.form.get("rental_vehicle_id", "").strip()
                daily_raw = request.form.get("rental_daily_price", "").strip().replace(",", ".")
                if not vehicle_id or not daily_raw:
                    error = "Informe o veiculo e o valor da diaria."
                else:
                    try:
                        daily_value = float(daily_raw)
                    except ValueError:
                        daily_value = -1

                    if daily_value < 0:
                        error = "Valor da diaria invalido."
                    else:
                        vehicles = load_vehicles()
                        found = False
                        for vehicle in vehicles:
                            if str(vehicle.get("id") or "") == vehicle_id:
                                vehicle["diaria_aluguel"] = f"{daily_value:.2f}"
                                found = True
                                break

                        if not found:
                            error = "Veiculo nao encontrado."
                        else:
                            save_vehicles(vehicles)
                            success = "Diaria de aluguel atualizada com sucesso."

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
                            "password": hash_password(password),
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
        reports = build_reports(start_date, end_date)

        return render_template(
            "gerencial.html",
            sellers_registry=load_sellers(),
            commissions_registry=load_commissions(),
            users_registry=load_users(),
            goals_registry=load_seller_goals(),
            vehicles_registry=load_vehicles(),
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
                    updated=False,
                    vehicles_registry=list(reversed(load_vehicles())),
                )

            vehicle = {"id": str(uuid4())[:8], **form_data, "status": "disponivel"}
            vehicles = load_vehicles()
            vehicles.append(vehicle)
            save_vehicles(vehicles)
            return redirect(url_for("cadastro", created="1"))

        created = request.args.get("created") == "1"
        updated = request.args.get("updated") == "1"
        return render_template(
            "cadastro.html",
            created=created,
            updated=updated,
            error=None,
            form_data={},
            vehicles_registry=list(reversed(load_vehicles())),
        )

    @app.route("/cadastro/<vehicle_id>/editar", methods=["GET", "POST"])
    def editar_cadastro(vehicle_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect

        vehicles = load_vehicles()
        vehicle_index = next((index for index, item in enumerate(vehicles) if item.get("id") == vehicle_id), None)
        if vehicle_index is None:
            return redirect(url_for("cadastro"))

        current_vehicle = vehicles[vehicle_index]

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

            if form_data.get("preco"):
                try:
                    form_data["preco"] = f"{_to_float_price(form_data.get('preco', '0')):.2f}"
                except Exception:
                    form_data["preco"] = form_data.get("preco")

            missing = [label for key, label in REQUIRED_FIELDS.items() if not form_data.get(key)]
            if missing:
                return render_template(
                    "editar_veiculo.html",
                    error=f"Preencha os campos obrigatorios: {', '.join(missing)}.",
                    form_data=form_data,
                    vehicle_id=vehicle_id,
                )

            updated_vehicle = dict(current_vehicle)
            updated_vehicle.update(form_data)
            vehicles[vehicle_index] = updated_vehicle
            save_vehicles(vehicles)
            return redirect(url_for("cadastro", updated="1"))

        return render_template(
            "editar_veiculo.html",
            error=None,
            form_data=current_vehicle,
            vehicle_id=vehicle_id,
        )

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
        sales = _read_json_array(SALES_FILE)
        sale_record = dict(sale)
        sale_record["nota_xml_path"] = create_nota_xml(sale_record)
        sales.append(sale_record)
        with open(SALES_FILE, "w", encoding="utf-8") as f:
            json.dump(sales, f, ensure_ascii=False, indent=2)
        sync_sales_to_db([sale_record])

    def load_sales() -> list[dict]:
        return _read_json_array(SALES_FILE)

    def load_rentals() -> list[dict]:
        return _read_json_array(RENTALS_FILE)

    def save_rental(rental: dict) -> None:
        rentals = load_rentals()
        rental_record = dict(rental)
        rentals.append(rental_record)
        with open(RENTALS_FILE, "w", encoding="utf-8") as file:
            json.dump(rentals, file, ensure_ascii=False, indent=2)
        sync_rentals_to_db([rental_record])

    def update_sale_xml_path(sale_id: str, xml_path: str) -> None:
        if not sale_id or not xml_path:
            return

        sales = load_sales()
        updated_sale = None

        for current_sale in sales:
            if str(current_sale.get("id") or "") == sale_id:
                current_sale["nota_xml_path"] = xml_path
                updated_sale = current_sale
                break

        if updated_sale is None:
            return

        with open(SALES_FILE, "w", encoding="utf-8") as file:
            json.dump(sales, file, ensure_ascii=False, indent=2)

        sync_sales_to_db([updated_sale])

    def ensure_sale_xml(sale: dict) -> str:
        xml_path = str(sale.get("nota_xml_path") or "").strip()
        if xml_path and os.path.exists(xml_path):
            return xml_path

        xml_path = create_nota_xml(sale)
        sale_id = str(sale.get("id") or "").strip()
        if sale_id:
            update_sale_xml_path(sale_id, xml_path)
        return xml_path

    def find_sale_by_id(sale_id: str) -> dict | None:
        for current_sale in load_sales():
            if str(current_sale.get("id") or "") == sale_id:
                return current_sale
        return None

    def _to_float_price(value: str) -> float:
        return _to_db_float(value)

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

    def parse_rental_date(value: str) -> datetime | None:
        try:
            return datetime.strptime((value or "").strip(), "%Y-%m-%d")
        except ValueError:
            return None

    def rental_overlaps_period(rental: dict, start_dt: datetime, end_dt: datetime) -> bool:
        status = str(rental.get("status") or "ativo").strip().lower()
        if status != "ativo":
            return False

        rental_start = parse_rental_date(str(rental.get("periodo_inicio") or ""))
        rental_end = parse_rental_date(str(rental.get("periodo_fim") or ""))
        if rental_start is None or rental_end is None:
            return False

        return rental_start <= end_dt and start_dt <= rental_end

    def get_vehicle_rental_overlap(vehicle_id: str, start_dt: datetime, end_dt: datetime) -> dict | None:
        for rental in load_rentals():
            if str(rental.get("vehicle_id") or "") != vehicle_id:
                continue
            if rental_overlaps_period(rental, start_dt, end_dt):
                return rental
        return None

    def vehicle_has_rental_overlap(vehicle_id: str, start_dt: datetime, end_dt: datetime) -> bool:
        return get_vehicle_rental_overlap(vehicle_id, start_dt, end_dt) is not None

    def vehicle_is_rented_today(vehicle_id: str) -> bool:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return vehicle_has_rental_overlap(vehicle_id, today, today)

    def list_available_vehicles_for_rental() -> list[dict]:
        available: list[dict] = []
        for vehicle in load_vehicles():
            if str(vehicle.get("status") or "") != "disponivel":
                continue
            vehicle_id = str(vehicle.get("id") or "")
            if vehicle_id and vehicle_is_rented_today(vehicle_id):
                continue
            available.append(vehicle)
        return available

    @app.route("/aluguel", methods=["GET"])
    def aluguel():
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect

        q = (request.args.get("q") or "").strip()
        vehicles = [dict(vehicle) for vehicle in list_available_vehicles_for_rental()]
        for vehicle in vehicles:
            daily_value = _to_float_price(vehicle.get("diaria_aluguel", "0"))
            vehicle["diaria_aluguel"] = f"{daily_value:.2f}"

        if q:
            query = q.lower()

            def matches(vehicle: dict) -> bool:
                text = " ".join([str(vehicle.get(key) or "") for key in ("marca", "modelo", "placa", "renavam")])
                return query in text.lower()

            vehicles = [vehicle for vehicle in vehicles if matches(vehicle)]

        rentals = load_rentals()
        recent_rentals = list(reversed(rentals[-10:]))

        return render_template(
            "aluguel.html",
            vehicles=vehicles,
            q=q,
            created=request.args.get("created") == "1",
            recent_rentals=recent_rentals,
        )

    @app.route("/aluguel/<vehicle_id>/novo", methods=["GET", "POST"])
    def novo_aluguel(vehicle_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect

        vehicles = load_vehicles()
        vehicle = next((item for item in vehicles if item.get("id") == vehicle_id), None)
        if vehicle is None or str(vehicle.get("status") or "") != "disponivel":
            return redirect(url_for("aluguel"))

        daily_value = _to_float_price(vehicle.get("diaria_aluguel", "0"))
        vehicle_view = dict(vehicle)
        vehicle_view["diaria_aluguel"] = f"{daily_value:.2f}"

        if request.method == "POST":
            form_data = request.form.to_dict()
            cliente_nome = (request.form.get("cliente_nome") or "").strip()
            cliente_cpf = (request.form.get("cliente_cpf") or "").strip()
            cliente_cnh = (request.form.get("cliente_cnh") or "").strip()
            cliente_endereco = (request.form.get("cliente_endereco") or "").strip()
            cliente_telefone = (request.form.get("cliente_telefone") or "").strip()
            periodo_inicio_raw = (request.form.get("periodo_inicio") or "").strip()
            periodo_fim_raw = (request.form.get("periodo_fim") or "").strip()
            retirada_em_casa = (request.form.get("retirada_em_casa") or "no") == "yes"
            valor_retirada_raw = (request.form.get("valor_retirada") or "").strip()
            forma_pagamento = (request.form.get("forma_pagamento") or "").strip()

            required = [
                cliente_nome,
                cliente_cpf,
                cliente_cnh,
                cliente_endereco,
                cliente_telefone,
                periodo_inicio_raw,
                periodo_fim_raw,
                forma_pagamento,
            ]
            if any(not value for value in required):
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="Preencha todos os campos obrigatorios do aluguel.",
                    form_data=form_data,
                )

            if not validate_cpf(cliente_cpf):
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="CPF invalido.",
                    form_data=form_data,
                )

            if daily_value <= 0:
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="Defina a diaria na tela gerencial antes de alugar.",
                    form_data=form_data,
                )

            periodo_inicio = parse_rental_date(periodo_inicio_raw)
            periodo_fim = parse_rental_date(periodo_fim_raw)
            if periodo_inicio is None or periodo_fim is None:
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="Periodo de aluguel invalido.",
                    form_data=form_data,
                )

            if periodo_fim < periodo_inicio:
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="Data final nao pode ser menor que a data inicial.",
                    form_data=form_data,
                )

            conflicting_rental = get_vehicle_rental_overlap(vehicle_id, periodo_inicio, periodo_fim)
            if conflicting_rental:
                conflict_start = str(conflicting_rental.get("periodo_inicio") or "").strip() or "data nao informada"
                conflict_end = str(conflicting_rental.get("periodo_fim") or "").strip() or "data nao informada"
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error=f"Essa data ja esta selecionada para esse carro ({conflict_start} ate {conflict_end}).",
                    form_data=form_data,
                )

            if retirada_em_casa and not valor_retirada_raw:
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="Informe o valor de retirada em casa.",
                    form_data=form_data,
                )

            valor_retirada = _to_float_price(valor_retirada_raw) if retirada_em_casa else 0.0
            if valor_retirada < 0:
                return render_template(
                    "alugar.html",
                    vehicle=vehicle_view,
                    error="Valor de retirada invalido.",
                    form_data=form_data,
                )

            quantidade_diarias = (periodo_fim - periodo_inicio).days + 1
            valor_base = quantidade_diarias * daily_value
            valor_total = valor_base + valor_retirada

            current_user = get_current_seller()
            rental = {
                "id": str(uuid4())[:8],
                "vehicle_id": vehicle_id,
                "vehicle": vehicle_view,
                "vendedor": current_user.get("name") or current_user.get("username") or "Sem vendedor",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cliente_nome": cliente_nome,
                "cliente_cpf": cliente_cpf,
                "cliente_cnh": cliente_cnh,
                "cliente_endereco": cliente_endereco,
                "cliente_telefone": cliente_telefone,
                "periodo_inicio": periodo_inicio_raw,
                "periodo_fim": periodo_fim_raw,
                "quantidade_diarias": quantidade_diarias,
                "valor_diaria": daily_value,
                "valor_base": valor_base,
                "retirada_em_casa": retirada_em_casa,
                "valor_retirada": valor_retirada,
                "forma_pagamento": forma_pagamento,
                "valor_total": valor_total,
                "status": "ativo",
            }
            save_rental(rental)
            return redirect(url_for("aluguel", created="1"))

        return render_template("alugar.html", vehicle=vehicle_view, error=None, form_data={})

    @app.route("/aluguel/<rental_id>/contrato", methods=["GET"])
    def contrato_rental(rental_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect

        rentals = load_rentals()
        rental = next((r for r in rentals if str(r.get("id") or "") == str(rental_id)), None)
        if rental is None:
            return redirect(url_for("aluguel"))

        # normalize numbers
        rental = dict(rental)
        try:
            rental["valor_total"] = float(rental.get("valor_total") or 0)
        except Exception:
            rental["valor_total"] = 0.0

        return render_template("contrato.html", rental=rental)

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
        sale["nota_xml_path"] = ensure_sale_xml(sale)
        return render_template("nota.html", sale=sale)

    @app.route("/vendas/nota/<sale_id>/xml", methods=["GET"])
    def download_nota_xml(sale_id: str):
        auth_redirect = require_authentication()
        if auth_redirect:
            return auth_redirect

        sale = find_sale_by_id(sale_id)
        if sale is None:
            return redirect(url_for("vendas"))

        xml_path = ensure_sale_xml(sale)
        return send_file(
            xml_path,
            mimetype="application/xml",
            as_attachment=True,
            download_name=f"nota-{sale_id}.xml",
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
