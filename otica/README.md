# Sistema Ótica

Cadastro de clientes, receitas (grau), vendas, pagamentos e entregas.
Feito em **Python + HTML + CSS** (sem framework de JavaScript). Funciona offline, no seu computador, e já está pronto para ir online.

## Como abrir (offline)

1. Instale o **Python 3.11 ou mais novo** em python.org. No Windows, marque **"Add python.exe to PATH"**.
2. **Windows:** dê dois cliques em `iniciar.bat`.
   **Mac/Linux:** no terminal, `./iniciar.sh`.
3. O navegador abre sozinho em `http://localhost:5000`. Para encerrar, feche a janela preta (ou `Ctrl+C`).

Na primeira vez ele instala o que precisa (precisa de internet só nesse momento). Depois funciona sem internet.

## Trazer os dados do sistema antigo (arquivo HTML)

No sistema antigo: **Backup / Celular → Baixar arquivo de dados**. No novo: **Backup → Importar arquivo .json** e escolha esse arquivo.

- Importar o mesmo arquivo duas vezes **não duplica** nada.
- O valor "pago" de cada venda antiga vira um pagamento.
- Vendas antigas com data de entrega no passado entram como **entregues**, para não lotar a lista de entregas pendentes.
- Receitas antigas entram com a data da última consulta cadastrada.

## Onde ficam os dados e os backups

Tudo está em **um arquivo**: `dados/otica.db`. O sistema guarda **uma cópia por dia** em `dados/backups` (as últimas 30).
Essas cópias estão no mesmo computador, então **de vez em quando baixe uma em Backup → Baixar cópia do banco e guarde em um pen drive ou na nuvem**.
Para restaurar: feche o sistema e substitua `dados/otica.db` por uma cópia.

## O que o sistema faz melhor que o anterior

| Antes | Agora |
|---|---|
| Dados no navegador (somem se limpar o histórico) | Arquivo de banco no disco + cópia diária |
| Um único campo "pago" | Lista de pagamentos (entrada, parcelas do carnê...) |
| Receita sobrescrita ao editar | Histórico de receitas por consulta |
| Venda à noite ficava com a data de amanhã | Data no fuso da loja |
| Dinheiro em decimal (erros de centavos) | Dinheiro em centavos inteiros |
| Importar de novo duplicava | Importação sem duplicar |
| Campos de entrega e consulta sem uso | Painel com **entregas pendentes** e **clientes para retorno** (com link de WhatsApp) |

## Subir online

O mesmo código roda online. A diferença é só o banco (PostgreSQL) e a **senha obrigatória**: o sistema se recusa a abrir para a internet sem `OTICA_SENHA`.

**Com Docker (em um servidor/VPS):**
```bash
cp .env.example .env     # preencha senhas e chave
docker compose up -d --build
```
Acesse `http://IP-DO-SERVIDOR:8000`. Para ter HTTPS (recomendado, pois há CPF e dados de saúde), coloque na frente um proxy como Caddy ou Nginx e depois defina `COOKIE_SEGURO=1`.

**Em plataformas que rodam Dockerfile** (Render, Railway...): crie um banco PostgreSQL no painel e configure as variáveis `DATABASE_URL`, `OTICA_SENHA`, `SECRET_KEY` e `FUSO`.

**Levar os dados do offline para o online:** no sistema offline, **Backup → Baixar arquivo .json**; no online, **Backup → Importar**.

| Variável | Para quê |
|---|---|
| `DATABASE_URL` | Banco PostgreSQL. Sem ela, usa o SQLite local |
| `OTICA_SENHA` | Senha de acesso. Obrigatória quando `HOST` não é local |
| `SECRET_KEY` | Chave do login (defina online para manter os acessos após reiniciar) |
| `FUSO` | Fuso da loja. Padrão `America/Sao_Paulo` |
| `HOST` / `PORT` | Endereço e porta (padrão `127.0.0.1` e `5000`) |
| `COOKIE_SEGURO` | `1` quando estiver em HTTPS |

Para usar no celular **dentro da loja** (mesmo Wi-Fi) com o computador ligado: defina `HOST=0.0.0.0` e `OTICA_SENHA=...` antes de iniciar e abra `http://IP-DO-COMPUTADOR:5000` no celular.

## Estrutura

```
app.py            liga tudo e inicia o servidor
banco.py          conexão (SQLite ou PostgreSQL) e backup diário
modelos.py        tabelas: clientes, receitas, vendas, pagamentos
util.py           datas, dinheiro, busca sem acento, WhatsApp
seguranca.py      senha opcional + proteção CSRF
importacao.py     exportar/importar JSON (formato novo e antigo)
rotas/            telas: clientes.py, vendas.py, sistema.py (início, backup, login)
templates/        páginas HTML
static/           estilo.css
testes/           testes automáticos
dados/            banco e backups (criados sozinhos)
```

## Testes

```bash
python -m unittest discover -s testes -v
```
Para testar no PostgreSQL, defina `TEST_DATABASE_URL` apontando para um banco **vazio de teste** (as tabelas dele são apagadas).

## Limites atuais

- **Uma senha para todos.** Não há usuários separados nem permissões. Para equipe, o próximo passo é login por usuário.
- Não há migrações automáticas de banco: se no futuro mudar a estrutura, será preciso atualizar as tabelas (ou exportar e importar o JSON).
- Buscas e listas carregam os registros na memória: ótimo para alguns milhares de clientes e vendas; para dezenas de milhares, vale paginar.
- Os dados incluem CPF e grau de lentes (dado de saúde, sensível pela LGPD): online, use sempre HTTPS, senha forte e backups.
