Bot inicial

Este diretório contém um esqueleto simples de bot para testes locais.

Comandos de exemplo:

```bash
python bot_inicio.py run --interval 1 --iterations 3
python bot_inicio.py test
```

O script usa apenas a biblioteca padrão do Python.
 
Modo interativo:

```bash
python bot_inicio.py interactive
```

No modo `interactive` o bot pedirá para identificar o usuário por email ou nome de usuário e apresentará opções de suporte, comercial e financeiro. Se o usuário não existir, o bot oferece registrar um lead (dados salvos em `leads.json`).

Iniciar versão web (Flask):

1. Instale dependências:

```bash
pip install -r requirements.txt
```

2. Rode o servidor:

```bash
python app.py
```

O app ficará disponível em `http://127.0.0.1:5000/` e oferece uma interface web para identificação de usuário e captura de leads.

Chat UI:

Após iniciar o servidor, acesse `http://127.0.0.1:5000/chat` para usar a interface de chat.

- Primeiro identifique-se por email ou usuário.
- Se for encontrado, envie uma opção: `suporte`, `financeiro` ou `comercial`.
- Se não for encontrado, será possível registrar um lead diretamente pelo chat.
