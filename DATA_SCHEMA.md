# Data Schema and Maintenance

This project persists data in JSON files at the project root.
All files use a root array (`[]`) with one object per record.

## Conventions

- File encoding: UTF-8
- Indentation: 2 spaces
- Root type: array
- `id` is required for every entity except `leads.json`
- Date-time format: `YYYY-MM-DD HH:MM:SS`
- Date format: `YYYY-MM-DD`

## Files

### `users.json`

Required fields:

- `id` (number)
- `username` (string)
- `name` (string)
- `email` (string, can be empty)
- `password` (string)
- `is_manager` (boolean)

### `sellers.json`

Required fields:

- `id` (string)
- `name` (string)
- `phone` (string, can be empty)
- `created_at` (string datetime)

### `commissions.json`

Required fields:

- `id` (string)
- `seller_name` (string)
- `percent` (number)
- `created_at` (string datetime)

### `seller_goals.json`

Required fields:

- `id` (string)
- `seller_name` (string)
- `target` (number)
- `created_at` (string datetime)

Optional fields:

- `updated_at` (string datetime)

### `vehicles.json`

Required fields:

- `id` (string)
- `marca` (string)
- `modelo` (string)
- `ano` (string)
- `renavam` (string)
- `placa` (string, uppercase preferred)
- `ipva_vencimento` (string date)
- `preco` (string decimal, ex: `25000.00`)
- `km` (string)
- `status` (string: `disponivel` or `vendido`)

Optional fields:

- `diaria_aluguel` (string or number decimal, ex: `350.00`)

### `sales.json`

Required fields:

- `id` (string)
- `vehicle_id` (string)
- `vehicle` (object snapshot)
- `vendedor` (string)
- `created_at` (string datetime)
- `cliente_nome` (string)
- `cliente_cpf` (string)
- `cliente_cnh` (string)
- `cliente_endereco` (string)
- `forma_pagamento` (string)
- `houve_negociacao` (boolean)
- `negociacao_desc` (string)
- `negociacao_valor` (number)
- `base_price` (number)
- `final_price` (number)

### `rentals.json`

Required fields:

- `id` (string)
- `vehicle_id` (string)
- `vehicle` (object snapshot)
- `vendedor` (string)
- `created_at` (string datetime)
- `cliente_nome` (string)
- `cliente_cpf` (string)
- `cliente_cnh` (string)
- `cliente_endereco` (string)
- `cliente_telefone` (string)
- `periodo_inicio` (string date)
- `periodo_fim` (string date)
- `quantidade_diarias` (number)
- `valor_diaria` (number)
- `valor_base` (number)
- `retirada_em_casa` (boolean)
- `valor_retirada` (number)
- `forma_pagamento` (string)
- `valor_total` (number)
- `status` (string: `ativo` or `encerrado`)

### `leads.json`

Recommended fields:

- `name` (string)
- `email` (string)
- `phone` (string)
- `company` (string)
- `message` (string)

## Maintenance Checklist

1. Keep all JSON files valid and pretty formatted.
2. Do not change root arrays to object wrappers without updating `app.py`.
3. Preserve field names expected by `app.py`.
4. Use `created_at` on newly inserted records.
