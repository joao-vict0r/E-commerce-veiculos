
#!/usr/bin/env python3
"""Bot inicial: esqueleto para iniciar e testar localmente.

Este script oferece 3 modos principais:
 - `run`: modo demo (heartbeat)
 - `test`: self-test rápido
 - `interactive`: fluxo interativo para identificar usuário e opções de suporte/comercial/financeiro

Ao não usar `interactive`, o script mantém compatibilidade com o antigo exemplo.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

LOG = logging.getLogger("bot_inicio")


DATA_DIR = os.path.dirname(__file__)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
LEADS_FILE = os.path.join(DATA_DIR, "leads.json")


class Bot:
	def __init__(self, name: str = "bot", interval: float = 2.0) -> None:
		self.name = name
		self.interval = interval
		self._running = False

	def start(self, iterations: Optional[int] = None) -> None:
		LOG.info("Starting %s (interval=%s)", self.name, self.interval)
		self._running = True
		i = 0
		try:
			while self._running:
				i += 1
				LOG.info("Heartbeat %s #%d", self.name, i)
				time.sleep(self.interval)
				if iterations is not None and i >= iterations:
					break
		except KeyboardInterrupt:
			LOG.info("Interrupted by user")
		finally:
			self._running = False
			LOG.info("Stopped %s", self.name)

	def stop(self) -> None:
		self._running = False


def setup_logging(level: int = logging.INFO) -> None:
	logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


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


def find_user(users: list[dict], identifier: str, by: str = "email") -> Optional[dict]:
	key = "email" if by == "email" else "username"
	for u in users:
		if u.get(key, "").lower() == identifier.lower():
			return u
	return None


def interactive_flow() -> int:
	setup_logging()
	users = load_users()
	print("--- Bot de Ajuda — Identificação do Usuário ---")
	method = ""
	while method not in ("1", "2"):
		method = input("Entrar com: (1) email, (2) usuário: ").strip()

	if method == "1":
		identifier = input("Informe o email: ").strip()
		user = find_user(users, identifier, by="email")
	else:
		identifier = input("Informe o nome de usuário: ").strip()
		user = find_user(users, identifier, by="username")

	if user:
		print(f"Olá {user.get('name', user.get('username'))}! Como posso ajudar hoje?")
		while True:
			print("Opções: 1) Suporte  2) Comercial  3) Financeiro  0) Sair")
			opt = input("Escolha uma opção: ").strip()
			if opt == "1":
				print("Você escolheu Suporte — redirecionando para o time de suporte (simulado).")
			elif opt == "2":
				print("Você escolheu Comercial — nosso time comercial entrará em contato.")
			elif opt == "3":
				print("Você escolheu Financeiro — iremos encaminhar ao setor financeiro.")
			elif opt == "0":
				print("Encerrando sessão. Obrigado!")
				break
			else:
				print("Opção inválida")
		return 0

	# não encontrou — oferecer cadastro como cliente
	print("Usuário não encontrado na base.")
	ans = input("Deseja se registrar como cliente para que o comercial entre em contato? (s/n): ").strip().lower()
	if ans == "s":
		name = input("Nome completo: ").strip()
		email = input("Email: ").strip()
		phone = input("Telefone: ").strip()
		company = input("Empresa (opcional): ").strip()
		message = input("Mensagem/Interesse: ").strip()
		lead = {"name": name, "email": email, "phone": phone, "company": company, "message": message}
		save_lead(lead)
		print("Obrigado — seus dados foram registrados. O time comercial entrará em contato.")
		return 0
	print("Operação cancelada.")
	return 0


def run_self_test() -> int:
	setup_logging(logging.DEBUG)
	LOG.info("Running self-test")
	b = Bot(interval=0.1)
	b.start(iterations=2)
	LOG.info("Self-test passed")
	return 0


def run_cli(argv: Optional[list[str]] = None) -> int:
	parser = argparse.ArgumentParser(description="Bot inicial — CLI de exemplo")
	sub = parser.add_subparsers(dest="cmd")

	p_run = sub.add_parser("run", help="Run the bot (heartbeat demo)")
	p_run.add_argument("--interval", "-i", type=float, default=2.0, help="Heartbeat interval (seconds)")
	p_run.add_argument("--iterations", type=int, default=3, help="Number of iterations (for demo)")

	sub.add_parser("test", help="Run self-tests")
	sub.add_parser("interactive", help="Start interactive user-help flow")

	args = parser.parse_args(argv)
	setup_logging()

	if args.cmd == "run":
		bot = Bot(interval=args.interval)
		bot.start(iterations=args.iterations)
		return 0
	if args.cmd == "test":
		return run_self_test()
	if args.cmd == "interactive":
		return interactive_flow()

	parser.print_help()
	return 1


if __name__ == "__main__":
	raise SystemExit(run_cli())
