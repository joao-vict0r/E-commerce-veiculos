from __future__ import annotations

import json
import os
from typing import Optional

from flask import Flask, redirect, render_template, request, url_for, session, jsonify

DATA_DIR = os.path.dirname(__file__)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
LEADS_FILE = os.path.join(DATA_DIR, "leads.json")


def load_users() -> list[dict]:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_lead(lead: dict) -> None:
    leads = []
    try:
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            leads = json.load(f)
    except FileNotFoundError:
        leads = []
    leads.append(lead)
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)


def find_user(identifier: str, by: str = "email") -> Optional[dict]:
    users = load_users()
    key = "email" if by == "email" else "username"
    for u in users:
        if u.get(key, "").lower() == identifier.lower():
            return u
    return None


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/chat", methods=["GET"])
    def chat():
        return render_template("chat.html")

    @app.route("/identify", methods=["POST"])
    def identify():
        method = request.form.get("method")
        identifier = request.form.get("identifier", "").strip()
        if method not in ("email", "username") or not identifier:
            return redirect(url_for("index"))

        user = find_user(identifier, by=method)
        if user:
            return render_template("menu.html", user=user)
        # not found -> show lead capture with prefilled email/username
        return render_template("lead_form.html", prefill={"identifier": identifier, "method": method})

    @app.route("/lead", methods=["POST"])
    def lead():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()
        message = request.form.get("message", "").strip()
        lead = {"name": name, "email": email, "phone": phone, "company": company, "message": message}
        save_lead(lead)
        return render_template("thanks.html")

    @app.route("/chat/message", methods=["POST"])
    def chat_message():
        data = request.get_json() or {}
        action = data.get("action")

        # Identify action: try to find user by email or username
        if action == "identify":
            method = data.get("method", "email")
            identifier = (data.get("identifier") or "").strip()
            if not identifier:
                return jsonify({"reply": "Por favor informe um email ou usuário."}), 400
            user = find_user(identifier, by=method)
            if user:
                session["user"] = user
                return jsonify({
                    "reply": f"Olá {user.get('name') or user.get('username')}. Como posso ajudar?",
                    "identified": True,
                    "buttons": ["Suporte", "Financeiro", "Comercial"],
                })
            return jsonify({"reply": "Usuário não encontrado. Deseja registrar como lead?", "identified": False, "buttons": ["Quero contato do comercial"]})

        # Option action: user must be identified
        if action == "option":
            user = session.get("user")
            if not user:
                return jsonify({"reply": "Usuário não identificado. Primeiro identifique-se."}), 400
            opt = (data.get("option") or "").lower()
            if opt == "suporte":
                return jsonify({"reply": "Você escolheu Suporte — nós abrimos um chamado para o time de suporte (simulado)."})
            if opt == "financeiro":
                return jsonify({"reply": "Você escolheu Financeiro — encaminhando ao financeiro (simulado)."})
            if opt == "comercial":
                return jsonify({"reply": "Você escolheu Comercial — o time comercial entrará em contato."})
            return jsonify({"reply": "Opção inválida. Escolha: suporte, financeiro ou comercial."})

        # Lead registration via chat
        if action == "lead":
            lead = {
                "name": data.get("name", "").strip(),
                "email": data.get("email", "").strip(),
                "phone": data.get("phone", "").strip(),
                "company": data.get("company", "").strip(),
                "message": data.get("message", "").strip(),
            }
            save_lead(lead)
            return jsonify({"reply": "Obrigado — seu contato foi registrado. O comercial entrará em contato.", "buttons": ["Tenho login", "Quero contato do comercial"]})

        return jsonify({"reply": "Ação desconhecida."}), 400

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
