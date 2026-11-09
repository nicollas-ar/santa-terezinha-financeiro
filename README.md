# Gestão Financeira Paroquial — versão avançada (protótipo)

## Funcionalidades
- Perfis padre e secretaria, com controle de acesso no servidor.
- Secretaria cadastra receitas e despesas e vê apenas seus lançamentos.
- Padre aprova/rejeita, vê saldos, gerencia contas e unidades e exporta CSV.
- Comunidades, campanhas, projetos e centros de custo; filtros por unidade.
- Vencimentos, referência de comprovante (texto) e marcação de despesas pagas.
- Auditoria básica de operações (não é trilha imutável).

## Instalação
1. Python 3.11+: `python -m venv .venv` e ative o ambiente.
2. `pip install -r requirements.txt`.
3. Copie `.env.example` para `.env`, preencha `DATABASE_URL` do Neon e uma `SECRET_KEY` aleatória e persistente. Para testes HTTP locais, `COOKIE_SECURE=0`.
4. **Banco novo:** `flask --app app init-db`.
5. Crie o primeiro padre: `flask --app app create-user`.
6. `flask --app app run` e abra http://127.0.0.1:5000.

## Render
- Envie a pasta para um repositório privado e crie um Web Service Python.
- Build: `pip install -r requirements.txt`; Start: `gunicorn app:app`.
- Variáveis: `DATABASE_URL`, `SECRET_KEY`, `COOKIE_SECURE=1`.
- Execute `init-db` e `create-user` em terminal seguro com acesso ao mesmo banco antes do primeiro acesso.
- Neon **hospeda o banco**, Render **hospeda o Flask**.

## Atualização do banco da versão anterior
**ATENÇÃO:** `db.create_all()` NÃO acrescenta colunas a tabelas existentes. Não execute o novo código contra banco antigo sem migração. Faça backup e aplique migrações revisadas (por exemplo, Alembic/Flask-Migrate), ou use um banco novo apenas para testes. Não apague registros financeiros existentes.

## Limitações importantes antes do uso real
- O resultado representa receitas e despesas **aprovadas e registradas**, não extrato bancário conciliado. A marcação `paga` não altera o cálculo do saldo; portanto não representa fluxo de caixa efetivamente pago.
- Filtro mensal usa **data de cadastro**, não data de competência ou de pagamento.
- O filtro de relatórios limita a 5.000 registros: totais de relatórios com mais registros ficam incompletos. CSV exporta todos os registros sem os filtros da tela.
- Ainda não há upload/armazenamento de comprovantes, conciliação bancária, orçamento por centro de custo, múltiplas alocações por lançamento, recorrência de contas, gráficos nem exportação PDF.
- Necessários para produção: migrações versionadas, backup e teste de restauração, MFA, recuperação segura de conta, limitação de tentativas de login, controle de sessão, HTTPS, proteção de logs e dados pessoais, trilha de auditoria resistente a adulteração, conciliação e revisão contábil, política LGPD.
- Use somente dados fictícios até que os controles de produção estejam implementados e testados.


## Personalização paroquial
A identidade visual usa a logo fornecida pela paróquia, o nome **Santa Terezinha do Menino Jesus** e a referência à **Capela Santa Luzia**.

Após atualizar o código no Render, execute **uma única vez** no terminal local conectado ao Neon:

```bash
flask --app app seed-parish-units
```

O comando é idempotente e não remove nem altera lançamentos existentes. A paróquia e a capela são cadastradas como unidades do tipo `comunidade`, para permitir filtros separados nos relatórios. Não execute `init-db` em um banco de produção sem antes avaliar o estado do banco. Não envie `.env` ao GitHub.