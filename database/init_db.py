from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import json
import sqlite3
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / 'database' / 'ecommerce_veiculos.db'
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / 'database' / 'schema.sql'

JSON_FILES = {
    'users': 'users.json',
    'sellers': 'sellers.json',
    'commissions': 'commissions.json',
    'seller_goals': 'seller_goals.json',
    'vehicles': 'vehicles.json',
    'sales': 'sales.json',
    'leads': 'leads.json',
}


def read_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return []

    return data if isinstance(data, list) else []


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    if value is None:
        return default

    txt = str(value).strip().replace('R$', '').replace(' ', '')
    if not txt:
        return default

    if txt.count(',') == 1 and '.' in txt:
        txt = txt.replace('.', '').replace(',', '.')
    else:
        txt = txt.replace(',', '.')

    try:
        return float(txt)
    except ValueError:
        return default


def as_bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def init_db(db_path: Path, schema_path: Path, reset: bool = False) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if reset and db_path.exists():
        db_path.unlink()

    schema_sql = schema_path.read_text(encoding='utf-8')

    with sqlite3.connect(db_path) as connection:
        connection.execute('PRAGMA foreign_keys = ON;')
        connection.executescript(schema_sql)
        sales_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sales)").fetchall()
        }
        if 'nota_xml_path' not in sales_columns:
            connection.execute('ALTER TABLE sales ADD COLUMN nota_xml_path TEXT')
        connection.commit()


def import_json_data(db_path: Path) -> dict[str, int]:
    stats = {
        'users': 0,
        'sellers': 0,
        'commissions': 0,
        'seller_goals': 0,
        'vehicles': 0,
        'sales': 0,
        'leads': 0,
    }

    with sqlite3.connect(db_path) as connection:
        connection.execute('PRAGMA foreign_keys = ON;')

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['users']):
            user_id = row.get('id')
            if user_id is not None:
                try:
                    user_id = int(user_id)
                except (TypeError, ValueError):
                    user_id = None

            connection.execute(
                '''
                INSERT OR REPLACE INTO users (
                    id, username, name, email, password, is_manager
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    user_id,
                    str(row.get('username') or '').strip(),
                    str(row.get('name') or row.get('username') or '').strip(),
                    str(row.get('email') or '').strip(),
                    str(row.get('password') or '').strip(),
                    as_bool_int(row.get('is_manager')),
                ),
            )
            stats['users'] += 1

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['sellers']):
            connection.execute(
                '''
                INSERT OR REPLACE INTO sellers (
                    id, name, phone, created_at
                ) VALUES (?, ?, ?, ?)
                ''',
                (
                    str(row.get('id') or '').strip(),
                    str(row.get('name') or '').strip(),
                    str(row.get('phone') or '').strip(),
                    str(row.get('created_at') or '').strip(),
                ),
            )
            stats['sellers'] += 1

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['commissions']):
            connection.execute(
                '''
                INSERT OR REPLACE INTO commissions (
                    id, seller_name, percent, created_at
                ) VALUES (?, ?, ?, ?)
                ''',
                (
                    str(row.get('id') or '').strip(),
                    str(row.get('seller_name') or '').strip(),
                    as_float(row.get('percent')),
                    str(row.get('created_at') or '').strip(),
                ),
            )
            stats['commissions'] += 1

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['seller_goals']):
            connection.execute(
                '''
                INSERT OR REPLACE INTO seller_goals (
                    id, seller_name, target, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    str(row.get('id') or '').strip(),
                    str(row.get('seller_name') or '').strip(),
                    as_int(row.get('target')),
                    str(row.get('created_at') or '').strip(),
                    str(row.get('updated_at') or '').strip() or None,
                ),
            )
            stats['seller_goals'] += 1

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['vehicles']):
            connection.execute(
                '''
                INSERT INTO vehicles (
                    id, marca, modelo, cor, ano, renavam, placa,
                    ipva_vencimento, preco, km, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    status = excluded.status
                ''',
                (
                    str(row.get('id') or '').strip(),
                    str(row.get('marca') or '').strip(),
                    str(row.get('modelo') or '').strip(),
                    str(row.get('cor') or '').strip() or None,
                    str(row.get('ano') or '').strip(),
                    str(row.get('renavam') or '').strip(),
                    str(row.get('placa') or '').strip().upper(),
                    str(row.get('ipva_vencimento') or '').strip(),
                    as_float(row.get('preco')),
                    str(row.get('km') or '').strip() or None,
                    str(row.get('status') or 'disponivel').strip(),
                ),
            )
            stats['vehicles'] += 1

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['sales']):
            connection.execute(
                '''
                INSERT OR REPLACE INTO sales (
                    id, vehicle_id, vehicle_snapshot, vendedor, created_at,
                    cliente_nome, cliente_cpf, cliente_cnh, cliente_endereco,
                    forma_pagamento, houve_negociacao, negociacao_desc,
                    negociacao_valor, base_price, final_price, nota_xml_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    str(row.get('id') or '').strip(),
                    str(row.get('vehicle_id') or '').strip(),
                    json.dumps(row.get('vehicle') or {}, ensure_ascii=False),
                    str(row.get('vendedor') or '').strip(),
                    str(row.get('created_at') or '').strip(),
                    str(row.get('cliente_nome') or '').strip(),
                    str(row.get('cliente_cpf') or '').strip(),
                    str(row.get('cliente_cnh') or '').strip(),
                    str(row.get('cliente_endereco') or '').strip(),
                    str(row.get('forma_pagamento') or '').strip(),
                    as_bool_int(row.get('houve_negociacao')),
                    str(row.get('negociacao_desc') or '').strip(),
                    as_float(row.get('negociacao_valor')),
                    as_float(row.get('base_price')),
                    as_float(row.get('final_price')),
                    str(row.get('nota_xml_path') or '').strip() or None,
                ),
            )
            stats['sales'] += 1

        for row in read_json_array(PROJECT_ROOT / JSON_FILES['leads']):
            connection.execute(
                '''
                INSERT INTO leads (
                    name, email, phone, company, message
                ) VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    str(row.get('name') or '').strip(),
                    str(row.get('email') or '').strip(),
                    str(row.get('phone') or '').strip(),
                    str(row.get('company') or '').strip(),
                    str(row.get('message') or '').strip(),
                ),
            )
            stats['leads'] += 1

        connection.commit()

    return stats


def count_tables(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            '''
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            '''
        ).fetchall()
    return [row[0] for row in rows]


def parse_args() -> tuple[Path, Path, bool, bool]:
    parser = ArgumentParser(description='Create SQLite database for E-commerce-veiculos.')
    parser.add_argument('--db-path', default=str(DEFAULT_DB_PATH))
    parser.add_argument('--schema-path', default=str(DEFAULT_SCHEMA_PATH))
    parser.add_argument('--reset', action='store_true', help='Delete existing DB before creating a new one.')
    parser.add_argument('--import-json', action='store_true', help='Import current JSON data into SQLite tables.')
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    schema_path = Path(args.schema_path)
    if not schema_path.is_absolute():
        schema_path = PROJECT_ROOT / schema_path

    return db_path, schema_path, args.reset, args.import_json


if __name__ == '__main__':
    db_path_arg, schema_path_arg, reset_arg, import_arg = parse_args()

    init_db(db_path_arg, schema_path_arg, reset=reset_arg)
    print(f'Database created at: {db_path_arg.resolve()}')

    if import_arg:
        imported = import_json_data(db_path_arg)
        print('Imported rows:')
        for key, value in imported.items():
            print(f'  - {key}: {value}')

    tables = count_tables(db_path_arg)
    print('Tables: ' + ', '.join(tables))
