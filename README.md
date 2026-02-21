# CarroFacil

Aplicacao Flask para gestao de veiculos com login e modulos operacionais:

- Area de Cadastro: cadastro de veiculos para venda.
- Area de Venda: visualizacao de estoque e marcacao de veiculos vendidos.
- Area de Aluguel: cadastro de contratos de aluguel com cliente, periodo e pagamento.
- Tela Gerencial: vendedores, comissoes, metas, acessos e diaria de aluguel por carro.

## Como executar

1. Instale dependencias:

```bash
pip install -r requirements.txt
```

2. Inicie o servidor:

```bash
python app.py
```

3. Acesse no navegador:

- Login: `http://127.0.0.1:5000/login`
- Painel principal: `http://127.0.0.1:5000/`
- Cadastro: `http://127.0.0.1:5000/cadastro`
- Vendas: `http://127.0.0.1:5000/vendas`
- Aluguel: `http://127.0.0.1:5000/aluguel`
- Gerencial: `http://127.0.0.1:5000/gerencial`

Credencial padrao de exemplo em `users.json`:

- Usuario: `joao`
- Senha: `123456`

## Persistencia de dados

- Veiculos: `vehicles.json`
- Vendas: `sales.json`
- Alugueis: `rentals.json`

## Regras de cadastro de veiculo

Campos obrigatorios:

- Marca
- Modelo
- Ano
- Renavam
- Placa
- Data de vencimento do IPVA

Campos opcionais:

- Preco
- Quilometragem
