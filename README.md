# Laticínio Braga — Sistema de leite e financeiro (Django)

Versão em **Django 5.2 + AdminLTE 4** do antigo app Streamlit (`crudf.py`).
Controla os produtores, o leite recebido todo dia, os recibos, os pagamentos aos produtores e o caixa (entradas e saídas).

---

## 1. Como iniciar

**Windows:** dê dois cliques em `iniciar.bat`
**ou**, em qualquer sistema, no terminal dentro da pasta:

```bash
python iniciar.py
```

Na primeira vez ele cria o `.venv`, instala as dependências, gera o `.env` com uma chave secreta, prepara o banco e abre o navegador em `http://127.0.0.1:8000`.

| Primeiro acesso | |
|---|---|
| Usuário | `admin` |
| Senha | `admin123` |

**Desligar:** `Ctrl + C` no terminal (ou feche a janela).

**Opções:**

| Comando | Para quê |
|---|---|
| `python iniciar.py --porta 8080` | usar outra porta |
| `python iniciar.py --sem-navegador` | não abrir o navegador |
| `python iniciar.py --rede` | liberar o acesso pelo celular/outros PCs do mesmo Wi-Fi |

### Trazer os dados do Streamlit

Copie o `financeiro.db` do sistema antigo para a pasta e rode (o banco antigo é aberto só para leitura):

```bash
.venv\Scripts\python.exe manage.py importar_streamlit financeiro.db --simular   # só mostra o que faria
.venv\Scripts\python.exe manage.py importar_streamlit financeiro.db             # importa de verdade
```

- nomes da tabela `leite` → **Produtores** (o preço padrão vira o último preço usado);
- linhas com data → **Coletas** (0 litros continua sendo **falta**; se houver duas no mesmo dia, vale a última);
- colunas `entrada1..10` / `saida1..10` da tabela `financ` → **Lançamentos** do caixa nas mesmas categorias.

Pode rodar mais de uma vez sem duplicar.

### Dados de demonstração

```bash
.venv\Scripts\python.exe manage.py popular_demo --usuarios
```
Cria 7 produtores, 90 dias de leite, pagamentos, caixa e os usuários `gerente / Gerente@2026`, `escritorio / Escritorio@2026` e `coletor / Coletor@2026`. **Não use num banco com dados reais.**

---

## 2. Módulos e como usar

| Menu | O que faz |
|---|---|
| **Painel** | Leite de hoje e do mês (com comparação com o mês anterior), produtores pendentes, saldo a pagar, caixa do mês, gráficos dos últimos 6 meses e alertas |
| **Coleta diária** ⭐ | Página do coletor, pensada para o celular. Só **insere** o leite de **hoje**: escolhe o produtor, marca **Coletado** ou **Entregue** e digita os litros. Não mostra preço, não edita e não apaga. Mostra quem ainda falta lançar (um toque já seleciona o produtor) e o que já foi lançado |
| **Calendário do leite** | O "calendário de folhinha" do Streamlit: digite os litros de cada dia e salve **tudo de uma vez**. Caixa *Falta* = 0 litros (aparece em vermelho no recibo). Campo vazio = sem lançamento. Navegação entre meses, histórico com corrigir/remover e **preço em massa** |
| **Produtores** | Cadastro com CPF, telefone (WhatsApp), chave Pix e **preço próprio do litro**. Renomear não perde o histórico. Produtor pode ser **inativado**; apagar só se não tiver pagamentos |
| **Emitir recibo** | Prévia por período, **imprimir**, **baixar PDF** (mesmo visual do antigo) e **enviar resumo pelo WhatsApp** |
| **Saldos a pagar** | Antigo "Relatório de Totais Devidos", agora descontando o que já foi pago. Saldo negativo = adiantamento |
| **Pagamentos** | Registra o pagamento ao produtor (dinheiro, Pix, misto, transferência, cheque). Gera **sozinho** a saída no caixa. Erro se corrige com **estorno** |
| **Financeiro** | Nova entrada / nova saída, extrato com filtros, totais e gráficos por categoria. **Categorias editáveis** (as 20 do Streamlit já vêm cadastradas) |
| **Dados do laticínio** | Nome, CPF/CNPJ, cidade e responsável que aparecem no recibo |
| **Backup** | Backup por e-mail automático, botão de enviar e de baixar |

### Regras importantes

- **Um lançamento por produtor por dia.** Se o coletor tentar lançar de novo, o sistema avisa e pede para o escritório corrigir.
- **Preço:** cada lançamento guarda o preço do dia. Mudar o preço do produtor só vale para os lançamentos novos; para corrigir os antigos use o *preço em massa*.
- **Nada some do caixa:** lançamentos e pagamentos são **estornados** (ficam riscados no histórico), nunca apagados.

### Coleta diária sem internet (modo offline)

A página do coletor funciona **sem sinal**:

1. **Com internet**, o coletor entra no sistema pelo celular e abre *Coleta diária*. No Chrome, toque em ⋮ → **Adicionar à tela inicial** (no iPhone: Compartilhar → *Adicionar à Tela de Início*). Pronto: o celular guardou a página e a lista de produtores.
2. **Sem internet**, ele abre o atalho normalmente e lança o leite. Aparece o aviso amarelo *"Sem internet"* e o card **Guardados no celular (N)**. O produtor some da lista *Falta lançar* e aparece em *Lançados hoje* com o selo **no celular**.
3. **Quando a internet volta**, os lançamentos são enviados sozinhos (ao reconectar, a cada minuto ou no botão **Enviar agora**). No Android o envio acontece até com a página fechada; no iPhone, ao abrir o atalho.

| Regra | Como funciona |
|---|---|
| Data | É a data **do celular** no momento do lançamento. O servidor aceita de hoje até `COLETA_OFFLINE_DIAS` dias atrás (padrão **7**), nunca no futuro |
| Preço | Continua vindo do cadastro do produtor (o celular nem conhece o preço) |
| Sem duplicar | Cada lançamento tem um código único. Se a internet cair no meio do envio, o reenvio é reconhecido e não grava duas vezes |
| Mesmo produtor no mesmo dia | O celular já bloqueia. Se o escritório lançou aquele produtor enquanto o celular estava offline, o item aparece em **Não aceitos pelo escritório** com o motivo — avise o escritório e toque em *Descartar* |
| Login | O coletor fica logado por `COLETOR_SESSAO_DIAS` dias (padrão 30). Se a sessão vencer, a fila **continua guardada** e a tela pede para entrar de novo |
| Outro usuário no mesmo celular | Os lançamentos só são enviados quando quem lançou estiver logado |

**Importante:** para a página **abrir** sem internet, o navegador exige **https** (na VPS com certificado) ou `localhost`. Pelo endereço da rede local (`http://192.168.x.x:8000`) a fila funciona enquanto a página estiver aberta, mas ela não abre do zero sem sinal. **Não limpe os dados do navegador** enquanto houver lançamentos *Guardados no celular*.

Arquivos: `static/js/coleta-fila.js` (fila no IndexedDB e envio), `static/js/coleta-offline.js` (tela), `templates/pwa/sw.js` (service worker) e `templates/pwa/manifest.webmanifest` (atalho). Mudou algum desses JS/CSS? Aumente `VERSAO_PWA` em `leite/views.py` para os celulares baixarem a versão nova.

---

## 3. Usuários e níveis de acesso

| Nível | Pode |
|---|---|
| **Administrador** | Tudo, inclusive usuários e níveis |
| **Gerente** | Tudo, menos usuários |
| **Escritório** | Produtores, calendário, recibos, pagamentos e caixa (sem estornar e sem apagar produtor) |
| **Coletor** | **Só a página de Coleta diária** (ao entrar, já cai nela) |

- *Usuários* → **Novo usuário**: uma senha provisória aparece **uma única vez**. A troca de senha só é exigida se você marcar **Exigir troca de senha** (no cadastro ou em Editar).
- *Níveis de acesso* → tabela de módulos × ações (ver/criar/editar/excluir + especiais). Crie quantos níveis quiser.
- O sistema não deixa o administrador tirar o próprio acesso nem ficar sem nenhum administrador ativo.

---

## 4. Formas de pagamento

Dinheiro, Pix, **Misto (dinheiro + Pix)**, transferência e cheque. No misto, dinheiro + Pix precisa fechar exatamente o valor (a tela completa o Pix sozinha).

---

## 5. Backup por e-mail

1. Menu **Backup** → preencha o e-mail de destino, o horário e os dados do SMTP.
2. **Gmail:** ative a verificação em duas etapas → acesse `myaccount.google.com/apppasswords` → crie uma senha de app "Laticínio" → cole os 16 caracteres no campo *Senha do e-mail*. Servidor `smtp.gmail.com`, porta `587`, TLS ligado.
3. Marque *Backup automático ligado* e salve. Use **Enviar backup agora** para testar.

- A senha fica **criptografada** no banco (Fernet, chave derivada da `SECRET_KEY`).
- O `.zip` tem o banco (`banco.sqlite3`), os dados em JSON, os logs e um LEIA-ME. **O `.env` nunca vai junto** — guarde uma cópia dele em lugar seguro.
- Ficam os 10 backups mais recentes na pasta `backups/`.
- Se o computador estava desligado no horário, o backup é feito assim que o sistema ligar.

**Restaurar** (com o sistema desligado):
```bash
.venv\Scripts\python.exe manage.py restaurar_backup backups\backup_laticinio_AAAA-MM-DD_HHMMSS.zip
```
O banco atual é guardado antes em `backups/antes_da_restauracao_*.sqlite3`.

Backup pelo terminal: `manage.py backup_agora` (ou `--enviar`).

---

## 6. Usar no celular (rede local)

1. Inicie com `python iniciar.py --rede` (ou ponha `ACESSO_REDE=True` no `.env`).
2. O terminal mostra o endereço, por exemplo `http://192.168.0.10:8000`.
3. No celular (mesmo Wi-Fi), abra esse endereço e entre com o usuário do coletor.
4. Dica: no Chrome do celular use "Adicionar à tela inicial" para virar um atalho.

Se o Windows perguntar sobre o Firewall, permita o acesso em **redes privadas**.

### Na internet (VPS Hostinger)

No `.env`: `ALLOWED_HOSTS=seu.dominio.com.br`, `CSRF_TRUSTED_ORIGINS=https://seu.dominio.com.br`, `USAR_HTTPS=True`. Rode o `manage.py servidor --sem-navegador` atrás do Nginx com certificado (Let's Encrypt). Confira com `manage.py check --deploy` (deve dar *no issues*). Para muitos acessos simultâneos, troque o SQLite por **PostgreSQL** (`pip install psycopg` e ajuste `DATABASES` no `settings.py`).

---

## 7. Testes automatizados

```bash
.venv\Scripts\python.exe manage.py test
```
70 testes: segurança (login obrigatório, bloqueio na 5ª senha, 403 por nível, CSRF, XSS, cabeçalhos, /admin/ escondido), usuários, coleta diária (só insere, data e preço do servidor), coleta offline (reenvio sem duplicar, janela de datas, conflito com o escritório, 401/403/CSRF da API, sessão longa do coletor), calendário, preço em massa, recibo/PDF, saldos, pagamentos e estornos, importação do Streamlit, caixa e backup (zip, e-mail, path traversal, agendador).

---

## 8. Estrutura do projeto

```
laticinio/
├── iniciar.py / iniciar.bat     # um comando para ligar
├── manage.py
├── requirements.txt / .env.example
├── config/          # settings.py (segurança), urls.py
├── core/            # painel, dados do laticínio, utilidades, validadores, filtros, comandos servidor e popular_demo
├── contas/          # login, troca de senha, usuários, níveis, middleware
├── leite/           # produtores, coleta diária, calendário, recibo (PDF), saldos, pagamentos, importar_streamlit
├── financeiro/      # caixa: categorias, lançamentos, extrato, estorno
├── backup/          # backup .zip, e-mail, agendador, restaurar
├── templates/       # telas (base.html + partials + uma pasta por app)
└── static/          # css/js do sistema e vendor/ (AdminLTE, Bootstrap, ícones, Chart.js - sem CDN)
```

| Arquivo | Para que serve |
|---|---|
| `*/models.py` | tabelas do banco |
| `*/servicos.py` | **regras de negócio** (as views só chamam estas funções) |
| `*/forms.py` | formulários e validações da tela |
| `*/views.py` | telas (todas são funções) |
| `*/urls.py` | endereços |
| `*/tests.py` | testes automatizados |
| `core/validadores.py` | CPF, CNPJ e telefone |
| `core/templatetags/formatos.py` | filtros `moeda` (R$ 1.234,56) e `litros` (1.234,5 L) |
| `contas/permissoes.py` | lista de permissões e níveis padrão |
| `contas/middleware.py` | obriga a trocar a senha quando o administrador exigir |
| `static/js/sistema.js` | confirmações, duplo clique, pagamento misto, falta no calendário |
| `static/js/graficos.js` | gráficos (Chart.js) a partir do `json_script` |

---

## 9. Segurança

| Medida | Protege contra |
|---|---|
| Login obrigatório em tudo (`LoginRequiredMiddleware`) | acesso sem senha |
| django-axes: 5 erros = bloqueio de 15 min | adivinhação de senha (força bruta) |
| Permissão conferida em **toda** view (`@permission_required`) | usuário abrindo endereço que não é do nível dele |
| Coleta diária: preço e "só inserir" decididos no servidor; data offline limitada a N dias | coletor alterar preço ou lançamentos antigos |
| API da fila offline: login, permissão, CSRF e código único por lançamento | envio por terceiros e lançamentos em dobro |
| Exclusões e estornos só por POST + CSRF | links maliciosos que apagam dados |
| Logout só por POST | deslogar alguém por um link |
| Templates com escape automático + `json_script` | XSS (scripts injetados) |
| `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy, COOP | clickjacking e vazamento de informações |
| `/admin/` trocado por endereço secreto do `.env` | robôs procurando o painel |
| `SECRET_KEY` no `.env`, `DEBUG=False` por padrão | vazamento de chave e de erros detalhados |
| Senha do e-mail criptografada (Fernet) | quem copiar só o banco |
| Download de backup conferido contra a lista | *path traversal* (baixar o `.env`) |
| Estorno no lugar de apagar | sumiço de histórico financeiro |
| Logs em `logs/seguranca.log` | investigar tentativas de invasão |
| `USAR_HTTPS=True`: HSTS, cookies seguros, redirecionamento | interceptação na internet |

---

## 10. Modo desenvolvimento e erros comuns

- **Programar:** no `.env` coloque `DEBUG=True` e rode `.venv\Scripts\python.exe manage.py runserver` — ou aperte **F5** no VS Code e escolha *Desenvolvimento (runserver)*. Volte para `DEBUG=False` ao terminar.
- **"Python não encontrado" / abre a Microsoft Store:** instale pelo python.org marcando *Add python.exe to PATH*; em *Configurações → Aplicativos → Aliases de execução* desligue os atalhos `python.exe` da Store.
- **PowerShell não ativa o .venv:** não precisa ativar, chame direto `.\.venv\Scripts\python.exe manage.py ...`
- **Usuário bloqueado:** tela *Usuários* → botão do cadeado, ou `.venv\Scripts\python.exe manage.py axes_reset_username NOME`
- **Esqueci a senha do admin:** `.venv\Scripts\python.exe manage.py changepassword admin`
- **Celular não abre:** confira se está no mesmo Wi-Fi, se iniciou com `--rede` e se o Firewall do Windows liberou o Python.

**Limitações:** não emite nota fiscal; o backup automático só roda com o sistema ligado; com SQLite, use no máximo algumas pessoas lançando ao mesmo tempo (para mais, PostgreSQL).
