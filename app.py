from __future__ import annotations

import json
import os
from typing import Any
from datetime import datetime
from uuid import uuid4

from flask import Flask, redirect, render_template, request, url_for

DATA_DIR = os.path.dirname(__file__)
VEHICLES_FILE = os.path.join(DATA_DIR, "vehicles.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

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

    def load_users() -> list[dict]:
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def get_current_seller() -> dict:
        users = load_users()
        env_user = os.environ.get("SELLER_USERNAME")
        if env_user:
            for u in users:
                if u.get("username") == env_user or u.get("email") == env_user:
                    return u
        return users[0] if users else {"username": "vendedor", "name": "Vendedor"}

    @app.context_processor
    def inject_user():
        return {"user": get_current_seller(), "sellers": load_users()}

    @app.route("/", methods=["GET"])
    def index():
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
