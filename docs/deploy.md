# Deployment Guide: Oracle Cloud ARM

This guide covers deploying the Imoveis DI FastAPI real estate monitoring app to Oracle Cloud ARM infrastructure.

## 1. Server Setup

Install required packages on your Oracle Cloud ARM instance:

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv git
```

## 2. Clone and Install

Clone the repository and install dependencies:

```bash
sudo mkdir -p /opt/imoveis-di
sudo git clone https://github.com/your-org/imoveis-di /opt/imoveis-di
cd /opt/imoveis-di
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 3. Configure Environment

Set up your environment configuration:

```bash
cp .env.example .env
```

Edit `/opt/imoveis-di/.env` to set the required variables:

- `WORKSPACE`: Path to workspace data directory (e.g., `/opt/imoveis-di/workspaces`)
- `SESSION_SECRET`: A secure random token for session management

Generate a secure `SESSION_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the output and update your `.env` file accordingly.

## 4. Initialize and Create User

Initialize the database and create an admin user:

```bash
cd /opt/imoveis-di
source .venv/bin/activate
python manage.py init-db
python manage.py create-user
```

Follow the prompts to set up your admin account.

## 5. Run with systemd

Create the systemd service unit file at `/etc/systemd/system/imoveis-di.service`:

```ini
[Unit]
Description=Imoveis DI
After=network.target

[Service]
WorkingDirectory=/opt/imoveis-di
EnvironmentFile=/opt/imoveis-di/.env
ExecStart=/opt/imoveis-di/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=on-failure
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable imoveis-di
sudo systemctl start imoveis-di
```

Verify the service is running:

```bash
sudo systemctl status imoveis-di
```

View logs:

```bash
sudo journalctl -u imoveis-di -f
```
