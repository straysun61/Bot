# DocBot 部署指南

## 快速开始

### 方式一：Docker 部署（推荐）

#### 1. 准备环境
```bash
# 安装 Docker 和 Docker Compose
# Ubuntu/Debian:
sudo apt update && sudo apt install docker.io docker-compose

# CentOS/RHEL:
sudo yum install docker docker-compose
sudo systemctl start docker && sudo systemctl enable docker
```

#### 2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
vi .env
```

至少需要配置：
```
OPENAI_API_KEY=sk-你的百炼API密钥
```

#### 3. 启动服务
```bash
# 仅启动应用（开发/测试）
docker compose up -d

# 带 Nginx 反向代理（生产环境）
docker compose --profile production up -d
```

#### 4. 访问
- 应用地址: `http://你的服务器IP:8000`
- 带 Nginx: `http://你的服务器IP`
- API 文档: `http://你的服务器IP:8000/docs`

#### 5. 常用命令
```bash
docker compose logs -f        # 查看日志
docker compose down           # 停止服务
docker compose pull && docker compose up -d  # 更新版本
```

---

### 方式二：宝塔面板部署

#### 1. 安装宝塔面板
```bash
# CentOS
yum install -y wget && wget -O install.sh https://download.bt.cn/install/install_6.0.sh && sh install.sh

# Ubuntu/Debian
wget -O install.sh https://download.bt.cn/install/install-ubuntu_6.0.sh && sudo bash install.sh
```

#### 2. 在宝塔中配置
1. 登录宝塔面板 → 软件商店 → 安装 **Python项目管理器**
2. 上传项目文件到服务器（通过宝塔文件管理或 FTP）
3. 在 Python项目管理器 中点击 **添加项目**：
   - 项目路径：选择上传的项目目录
   - 运行方式：Gunicorn / Uvicorn
   - 端口：8000
   - Python版本：3.11
4. 安装依赖（在项目管理器中点击「模块」→ 输入 `requirements.txt` 安装）
5. 配置 `.env` 文件（在文件管理中编辑）
6. 启动项目

#### 3. 配置域名和 SSL
1. 在宝塔「网站」→ 添加站点 → 绑定域名
2. 设置反向代理：目标 URL `http://127.0.0.1:8000`
3. 申请 SSL 证书（Let's Encrypt 免费）
4. 在站点配置中增加请求体大小限制：`client_max_body_size 100M;`

---

### 方式三：云服务器手动部署

#### 1. 环境准备
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip nginx

# CentOS/RHEL
sudo yum install -y python3.11 python3.11-devel nginx
```

#### 2. 创建虚拟环境
```bash
cd /opt/docbot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. 配置 systemd 服务
```bash
sudo tee /etc/systemd/system/docbot.service << 'EOF'
[Unit]
Description=DocBot Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/docbot
Environment=PATH=/opt/docbot/venv/bin
ExecStart=/opt/docbot/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable docbot
sudo systemctl start docbot
```

#### 4. 配置 Nginx
```bash
sudo tee /etc/nginx/sites-available/docbot << 'EOF'
server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_read_timeout 600s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/docbot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 安全注意事项

1. **必须修改 `.env` 中的 `SECRET_KEY`**，使用强随机字符串
2. **不要将 `.env` 文件提交到 Git**（已在 `.gitignore` 中排除）
3. **生产环境建议配置 HTTPS**（使用 Let's Encrypt 免费证书）
4. **限制文件上传大小**，防止恶意上传
5. **配置防火墙**，只开放 80/443 端口

## 获取百炼 API Key

1. 访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/)
2. 创建 API Key
3. 填入 `.env` 的 `OPENAI_API_KEY` 字段
