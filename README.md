# ERP de Veículos

Aplicação Flask simples para gestão de estoque de veículos com duas áreas principais:

- **Área de Cadastro**: cadastro de veículos para venda.
- **Área de Venda**: visualização de estoque e marcação de veículos como vendidos.

## Como executar

1. Instale dependências:

```bash
pip install -r requirements.txt
```

2. Inicie o servidor:

```bash
python app.py
```

3. Acesse no navegador:

- Painel principal: `http://127.0.0.1:5000/`
- Cadastro: `http://127.0.0.1:5000/cadastro`
- Vendas: `http://127.0.0.1:5000/vendas`

## Persistência de dados

Os dados dos veículos são salvos em `vehicles.json`.

## Regras de cadastro

Campos obrigatórios na área de cadastro:

- Marca
- Modelo
- Ano
- Renavam
- Placa
- Data de vencimento do IPVA

Campos opcionais:

- Preço
- Quilometragem

