# CarroFácil

Aplicação Flask simples para gestão de estoque de veículos com tela de login de segurança e duas áreas principais:

- **Área de Cadastro**: cadastro de veículos para venda.
- **Área de Venda**: visualização de estoque e marcação de veículos como vendidos.
- **Tela Gerencial**: cadastro de comissão, cadastro de vendedor e criação de novos acessos com permissão gerencial.

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

- Login: `http://127.0.0.1:5000/login`
- Painel principal (após login): `http://127.0.0.1:5000/`
- Cadastro: `http://127.0.0.1:5000/cadastro`
- Vendas: `http://127.0.0.1:5000/vendas`
- Gerencial: `http://127.0.0.1:5000/gerencial`

Credencial padrão de exemplo em `users.json`:

- Usuário: `joao`
- Senha: `123456`

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
