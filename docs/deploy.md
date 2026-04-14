# Deploy em Produção

Guia para hospedar o Imoveis DI (e outros apps) num servidor Linux com HTTPS automático.

---

## Visão geral da arquitetura

O objetivo final é um servidor único expondo múltiplos apps por subdomínio:

```
seu-dominio.com.br
├── imoveis.seu-dominio.com.br  → Imoveis DI    (porta 8000)
├── n8n.seu-dominio.com.br      → n8n            (porta 5678)
└── fin.seu-dominio.com.br      → Dashboard fin. (porta 8001)
```

**Caddy** atua como reverse proxy na frente, gerencia certificados TLS automaticamente via Let's Encrypt.

---

## 1. Escolha do servidor

### Oracle Cloud Free Tier (ARM) — quando disponível

- 4 vCPUs Ampere A1 + 24 GB RAM (compartilháveis entre instâncias)
- Sempre gratuito, mas disponibilidade é escassa em algumas regiões
- Imagem recomendada: **Ubuntu 22.04 LTS** (ARM64)

### Alternativas se Oracle não estiver disponível

| Provedor | Plano | Custo aprox. | RAM | Notas |
|----------|-------|-------------|-----|-------|
| **Hetzner** | CAX11 (ARM) | ~€3,5/mês | 4 GB | Melhor custo-benefício da Europa |
| **Hetzner** | CX22 (x86) | ~€4/mês | 4 GB | Mais disponibilidade |
| **DigitalOcean** | Basic Droplet | ~$6/mês | 1 GB | OK para só imoveis, apertado com n8n |
| **Vultr** | Cloud Compute | ~$6/mês | 2 GB | Similar ao DO |
| **Contabo** | VPS S | ~€4/mês | 8 GB | Muito RAM pelo preço, latência maior |

> Para rodar imoveis-di + n8n + dashboard: mínimo **2 GB RAM**, recomendado **4 GB**.
> Playwright (Chromium) consome ~200-400 MB durante o scraping.

---

## 2. Preparação do servidor

```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Dependências base
sudo apt install -y python3.11 python3.11-venv python3-pip git curl

# Instalar uv (gerenciador de pacotes Python — mais rápido que pip)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### Configurar firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp     # HTTP (redirecionado para HTTPS pelo Caddy)
sudo ufw allow 443/tcp    # HTTPS
sudo ufw enable
```

> **Oracle Cloud**: além do ufw, é necessário abrir as portas nas Security Lists da VCN
> pelo painel web (Networking → Virtual Cloud Networks → Security Lists).

---

## 3. Instalar Caddy (reverse proxy)

Caddy cuida de HTTPS automático — sem configurar certbot manualmente.

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

---

## 4. Deploy do Imoveis DI

```bash
sudo mkdir -p /opt/apps/imoveis-di
sudo chown $USER:$USER /opt/apps/imoveis-di

git clone <repo-url> /opt/apps/imoveis-di
cd /opt/apps/imoveis-di

# Criar virtualenv e instalar dependências
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Instalar Chromium para Playwright
playwright install chromium
playwright install-deps chromium   # dependências do sistema
```

### Configurar .env

```bash
nano /opt/apps/imoveis-di/.env
```

Conteúdo:

```env
WORKSPACE=/opt/apps/imoveis-di/workspaces/imoveis.db
SESSION_SECRET=<gere abaixo>
ENV=production
```

Gerar SESSION_SECRET:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Inicializar banco e criar usuário

```bash
cd /opt/apps/imoveis-di
source .venv/bin/activate
python manage.py init-db
python manage.py create-user
```

### Serviço systemd

Crie `/etc/systemd/system/imoveis-di.service`:

```ini
[Unit]
Description=Imoveis DI
After=network.target

[Service]
WorkingDirectory=/opt/apps/imoveis-di
EnvironmentFile=/opt/apps/imoveis-di/.env
ExecStart=/opt/apps/imoveis-di/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
User=ubuntu
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable imoveis-di
sudo systemctl start imoveis-di
sudo systemctl status imoveis-di
```

---

## 5. Deploy do n8n

n8n é um orquestrador de automações (similar ao Zapier, autohosted).

```bash
# Instalar Node.js LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Instalar n8n globalmente
sudo npm install -g n8n

# Criar diretório de dados
sudo mkdir -p /opt/apps/n8n-data
sudo chown $USER:$USER /opt/apps/n8n-data
```

Serviço systemd `/etc/systemd/system/n8n.service`:

```ini
[Unit]
Description=n8n workflow automation
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/apps/n8n-data
Environment=N8N_PORT=5678
Environment=N8N_HOST=0.0.0.0
Environment=N8N_PROTOCOL=https
Environment=WEBHOOK_URL=https://n8n.seu-dominio.com.br
Environment=N8N_USER_MANAGEMENT_JWT_SECRET=<gere com: openssl rand -hex 32>
Environment=N8N_ENCRYPTION_KEY=<gere com: openssl rand -hex 32>
Environment=DB_TYPE=sqlite
Environment=DB_SQLITE_DATABASE=/opt/apps/n8n-data/database.sqlite
ExecStart=/usr/bin/n8n start
Restart=on-failure
RestartSec=5
User=ubuntu
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable n8n
sudo systemctl start n8n
```

> Na primeira vez que acessar `https://n8n.seu-dominio.com.br`, o n8n pedirá para criar o usuário admin.

---

## 6. Dashboard de finanças pessoais

*(Placeholder — a ser preenchido quando a stack for definida.)*

Se for outro app FastAPI/Python:

```bash
sudo mkdir -p /opt/apps/financas
# clone + venv + install...
```

Serviço systemd `/etc/systemd/system/financas.service`:

```ini
[Unit]
Description=Dashboard Finanças
After=network.target

[Service]
WorkingDirectory=/opt/apps/financas
EnvironmentFile=/opt/apps/financas/.env
ExecStart=/opt/apps/financas/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8001
Restart=on-failure
User=ubuntu

[Install]
WantedBy=multi-user.target
```

---

## 7. Configurar Caddy (reverse proxy + HTTPS)

Edite `/etc/caddy/Caddyfile`:

```caddyfile
imoveis.seu-dominio.com.br {
    reverse_proxy localhost:8000
}

n8n.seu-dominio.com.br {
    reverse_proxy localhost:5678
}

fin.seu-dominio.com.br {
    reverse_proxy localhost:8001
}
```

> Substitua `seu-dominio.com.br` pelo seu domínio real.
> Os registros DNS (tipo A) para cada subdomínio devem apontar para o IP do servidor.

Recarregar Caddy:

```bash
sudo systemctl reload caddy
sudo systemctl status caddy
```

Caddy vai buscar e renovar os certificados Let's Encrypt automaticamente.

---

## 8. DNS

No painel do seu registrador de domínio, crie registros **A** para cada subdomínio:

```
imoveis.seu-dominio.com.br  →  <IP do servidor>
n8n.seu-dominio.com.br      →  <IP do servidor>
fin.seu-dominio.com.br      →  <IP do servidor>
```

Propagação pode levar até 24h, mas geralmente é minutos.

---

## Operação

### Ver logs em tempo real

```bash
sudo journalctl -u imoveis-di -f
sudo journalctl -u n8n -f
```

### Reiniciar após update

```bash
cd /opt/apps/imoveis-di
git pull
source .venv/bin/activate
pip install -r requirements.txt   # se requirements mudaram
sudo systemctl restart imoveis-di
```

### Backup do banco

```bash
# Backup simples — SQLite suporta cópia enquanto app está rodando
cp /opt/apps/imoveis-di/workspaces/imoveis.db \
   /opt/apps/imoveis-di/workspaces/imoveis.db.bak-$(date +%Y%m%d)
```

Para backup automático diário, adicione ao crontab (`crontab -e`):

```cron
0 3 * * * cp /opt/apps/imoveis-di/workspaces/imoveis.db /opt/apps/imoveis-di/workspaces/imoveis.db.bak-$(date +\%Y\%m\%d) && find /opt/apps/imoveis-di/workspaces -name "*.bak-*" -mtime +7 -delete
```

---

## Recursos de memória esperados (idle)

| App | RAM aprox. |
|-----|-----------|
| imoveis-di (uvicorn) | ~80 MB |
| n8n | ~200 MB |
| dashboard finanças | ~80 MB |
| Chromium (durante scraping) | +300 MB |
| **Total necessário** | **~2 GB** |

Servidor com 4 GB (Hetzner CAX11 ou Oracle ARM) tem margem confortável.
