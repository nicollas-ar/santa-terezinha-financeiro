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

## Caixa único: Matriz e Capela Santa Luzia
A **Paróquia Santa Terezinha do Menino Jesus** possui **um único financeiro consolidado**.
- Os lançamentos podem ser vinculados à **Matriz Santa Terezinha do Menino Jesus** ou à **Capela Santa Luzia**.
- O dashboard geral soma cada lançamento aprovado apenas uma vez; o comparativo por origem não cria caixa bancário separado.
- Lançamentos de projetos, campanhas e sem unidade ficam em **Geral / outros projetos**, permitindo reconciliação com o total.
- Os filtros por unidade permitem consultar Matriz ou Capela individualmente.
- O perfil `padre` visualiza comparativos; a secretaria continua vendo apenas os próprios registros.

**Depois de atualizar o Render**, execute uma vez (e com a mesma `DATABASE_URL` do Neon usada no Render):
```bash
flask --app app seed-parish-units
```
O comando pode ser executado novamente sem criar cópias. Caso exista apenas a antiga unidade `Santa Terezinha do Menino Jesus`, ela é renomeada para Matriz preservando o ID e os lançamentos existentes. Caso existam ambas, o sistema não faz uma migração automática potencialmente ambígua. Faça backup antes de executar em banco com dados reais.

Observação: projetos e campanhas continuam como unidades de classificação independentes; esta versão não implementa dupla alocação de um mesmo lançamento a local e projeto simultaneamente.


## Permissões por secretaria, horários de missas e coletas

- O padre pode criar contas com nível **Somente coletas**, **Receitas e despesas** ou **Ambos** e alterar a escolha em **Usuários**. A autorização é verificada no Flask, não apenas no menu.
- Secretarias antigas que ainda não têm configuração continuam com o acesso anterior a lançamentos (não recebem automaticamente acesso às coletas).
- Em **Missas e coletas**, o padre cadastra missas semanais (dia da semana) e mensais (dia do mês), com horário, local e data inicial.
- Em **Registrar coleta**, a pessoa escolhe uma celebração dos últimos sete dias, informa um valor e confirma. A data e o local são preenchidos automaticamente. Botões e campos são amplos para facilitar o uso.
- Cada missa/ocorrência aceita uma coleta registrada. Ela fica **pendente** até o padre aprovar. Só então é criado um lançamento aprovado de receita **Coleta** no caixa paroquial consolidado, atribuído à Matriz ou à Capela Santa Luzia.
- Desativar uma missa interrompe o aparecimento de novas ocorrências; os registros históricos permanecem.
- Dias 29, 30 e 31 não são gerados em meses que não têm esses dias. Esta versão não prevê missas extraordinárias, remarcação de coletas rejeitadas ou edição de coletas após o envio; nesses casos deve ser definido um procedimento administrativo.

### Atualização obrigatória do Neon existente
**Antes de fazer login após o deploy desta versão**, execute no terminal local com o mesmo `DATABASE_URL` configurado no Render:

```bash
flask --app app upgrade-collections
flask --app app seed-parish-units
```

O primeiro comando cria três tabelas novas (`staff_permission`, `mass_schedule`, `mass_collection`), sem apagar ou modificar as tabelas financeiras existentes. O segundo assegura que Matriz e Capela estejam cadastradas. Faça backup do banco antes da atualização. Não repita `create-user`: a conta do padre continua no banco.

**Importante:** esta é uma evolução de protótipo, ainda não validada para uso financeiro real; faltam testes integrados, backup/restauração, proteção de dados e procedimentos de conferência.

## Dízimos e doações por Pix

Em um banco existente, execute `flask --app app upgrade-contributions` antes de abrir o novo painel. O comando cria somente a tabela de contribuições e pode ser repetido. Use `flask --app app seed-parish-units` se a Matriz e a Capela ainda precisarem ser cadastradas.

Para ativar a página pública `/contribuir`, configure no Render as variáveis abaixo com os dados da conta da paróquia. Prefira uma chave institucional, pois ela fica visível no código Pix.

- `PARISH_PIX_KEY` — chave Pix cadastrada no banco, no formato aceito pelo Pix.
- `PARISH_PIX_NAME` — nome do recebedor, com até 25 caracteres.
- `PARISH_PIX_CITY` — cidade do recebedor, com até 15 caracteres.

O padre encontra **Dízimos e doações** no menu e pode compartilhar o endereço da página pública, inclusive no WhatsApp. O QR Code e o código copia e cola são gerados com o valor escolhido e uma referência Pix (TxId). A página não solicita nome ou CPF.

Gerar o código cria um registro pendente. Só confirme após conferir no banco a referência e o valor do pagamento. Use o identificador EndToEnd do extrato para evitar que o mesmo pagamento seja lançado duas vezes. A confirmação cria uma única receita de Dízimo ou Doação para a unidade escolhida, no caixa consolidado. Este fluxo usa conferência manual e requer que o banco informe o TxId e o EndToEnd no extrato ou na área de consulta de Pix recebidos. Antes de divulgar o endereço, teste com a conta institucional e confira os dois identificadores e o valor.

### Checkout Pix com confirmação automática e lembretes no WhatsApp

Execute `flask --app app upgrade-contributions` novamente para criar as novas tabelas, e `flask --app app enable-pix-ledger` para criar o usuário técnico de auditoria. O usuário técnico fica inativo para login. Configure `PARISH_PUBLIC_URL` com a origem HTTPS pública do app, sem caminho ou barra final. Use um ambiente e um banco separados para os testes.

**Asaas.** Configure `ASAAS_MODE=sandbox` no ambiente de testes ou `ASAAS_MODE=production` no ambiente paroquial, `ASAAS_API_KEY` e `ASAAS_WEBHOOK_TOKEN` (segredo aleatório de pelo menos 32 caracteres, diferente da chave da API). No mesmo ambiente do Asaas, cadastre o webhook para `POST /integracoes/asaas`, com o mesmo segredo, no modo sequencial, para `CHECKOUT_PAID`, `CHECKOUT_CANCELED` e `CHECKOUT_EXPIRED`. Confira no Sandbox os dados que o Checkout pede do fiel, o link de retorno e o conteúdo do webhook.

Com o Asaas habilitado, novas contribuições de R$ 5,00 ou mais usam o checkout hospedado pelo Asaas. O Asaas pode solicitar dados do pagador. A tela paroquial aguarda o evento autenticado de pagamento e exibe a confirmação após o lançamento. O lançamento registra o valor bruto. Use o extrato do Asaas para conciliar taxas e eventuais devoluções, que ainda não geram ajustes automáticos. Contribuições com códigos Pix estáticos já emitidos continuam no fluxo manual. A página de status confirma o pagamento ao fiel. Ela não envia recibo pelo WhatsApp.

**WhatsApp.** Configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` no formato `whatsapp:+55...` e `TWILIO_REMINDER_CONTENT_SID` com o SID de um modelo aprovado para WhatsApp. No remetente, configure a URL de mensagens recebidas como `POST /integracoes/whatsapp` na origem pública exata, sem parâmetros. O fiel ativa os lembretes enviando **QUERO LEMBRETES** do próprio WhatsApp. Ele pode sair com **SAIR**.

O modelo aprovado precisa ter duas variáveis. A primeira é o trecho que o padre edita, com até 120 caracteres e uma linha. A segunda é o endereço da página de contribuição. Exemplo de estrutura para submeter à aprovação:

> Olá! Este é o lembrete mensal de dízimo da Paróquia Santa Terezinha. {{1}} Para contribuir com segurança, acesse {{2}}. Para deixar de receber lembretes, responda SAIR.

O padre escolhe o dia (1 a 28), o horário de São Paulo e o trecho editável no painel. Os lembretes começam desativados. Para executar os envios, configure um Cron Job no Render, com a mesma revisão de código, o build `pip install -r requirements.txt`, o comando `flask --app app send-parish-reminders` e o agendamento `*/5 * * * *`. O job usa as mesmas variáveis de banco, Asaas/Pix e WhatsApp. Ele executa em UTC e converte para o horário de São Paulo dentro da aplicação.

Cada telefone autorizado recebe no máximo uma tentativa por mês, em lotes de até 50. O painel diferencia tentativas aceitas pelo provedor de falhas e envios em processamento. Em caso de falha ou queda durante o envio, consulte os logs do Twilio antes de qualquer reenvio. A confirmação de entrega ao celular não é exibida no painel. Teste o número e o template com um contato de teste que tenha aderido antes de ativar o envio da paróquia.
