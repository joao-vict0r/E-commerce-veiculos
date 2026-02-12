from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from flask import Flask, redirect, render_template, request, url_for

DATA_DIR = os.path.dirname(__file__)
VEHICLES_FILE = os.path.join(DATA_DIR, "vehicles.json")

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
                "ano": request.form.get("ano", "").strip(),
                "renavam": request.form.get("renavam", "").strip(),
                "placa": request.form.get("placa", "").strip().upper(),
                "ipva_vencimento": request.form.get("ipva_vencimento", "").strip(),
                "preco": request.form.get("preco", "").strip(),
                "km": request.form.get("km", "").strip(),
            }

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
        vehicles = load_vehicles()
        return render_template("vendas.html", vehicles=vehicles)

    @app.route("/vendas/<vehicle_id>/vender", methods=["POST"])
    def vender(vehicle_id: str):
        vehicles = load_vehicles()
        for vehicle in vehicles:
            if vehicle["id"] == vehicle_id:
                vehicle["status"] = "vendido"
                break
        save_vehicles(vehicles)
        return redirect(url_for("vendas"))

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
