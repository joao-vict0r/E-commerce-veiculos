PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL,
    is_manager INTEGER NOT NULL DEFAULT 0 CHECK (is_manager IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sellers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commissions (
    id TEXT PRIMARY KEY,
    seller_name TEXT NOT NULL,
    percent REAL NOT NULL CHECK (percent >= 0 AND percent <= 100),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seller_goals (
    id TEXT PRIMARY KEY,
    seller_name TEXT NOT NULL UNIQUE,
    target INTEGER NOT NULL CHECK (target >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY,
    marca TEXT NOT NULL,
    modelo TEXT NOT NULL,
    cor TEXT,
    ano TEXT NOT NULL,
    renavam TEXT NOT NULL,
    placa TEXT NOT NULL UNIQUE,
    ipva_vencimento TEXT NOT NULL,
    preco REAL NOT NULL DEFAULT 0 CHECK (preco >= 0),
    km TEXT,
    status TEXT NOT NULL DEFAULT 'disponivel' CHECK (status IN ('disponivel', 'vendido')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales (
    id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    vehicle_snapshot TEXT NOT NULL,
    vendedor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    cliente_nome TEXT NOT NULL,
    cliente_cpf TEXT NOT NULL,
    cliente_cnh TEXT NOT NULL,
    cliente_endereco TEXT NOT NULL,
    forma_pagamento TEXT NOT NULL,
    houve_negociacao INTEGER NOT NULL DEFAULT 0 CHECK (houve_negociacao IN (0, 1)),
    negociacao_desc TEXT,
    negociacao_valor REAL NOT NULL DEFAULT 0 CHECK (negociacao_valor >= 0),
    base_price REAL NOT NULL CHECK (base_price >= 0),
    final_price REAL NOT NULL CHECK (final_price >= 0),
    nota_xml_path TEXT,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    company TEXT,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_sellers_name ON sellers(name);
CREATE INDEX IF NOT EXISTS idx_commissions_seller_name ON commissions(seller_name);
CREATE INDEX IF NOT EXISTS idx_goals_seller_name ON seller_goals(seller_name);
CREATE INDEX IF NOT EXISTS idx_vehicles_status ON vehicles(status);
CREATE INDEX IF NOT EXISTS idx_vehicles_marca_modelo ON vehicles(marca, modelo);
CREATE INDEX IF NOT EXISTS idx_sales_vehicle_id ON sales(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_sales_vendedor ON sales(vendedor);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);

CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
AFTER UPDATE ON users
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE users
    SET updated_at = datetime('now')
    WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_vehicles_updated_at
AFTER UPDATE ON vehicles
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE vehicles
    SET updated_at = datetime('now')
    WHERE id = OLD.id;
END;
