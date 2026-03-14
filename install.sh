#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURRENT_USER="$(whoami)"
SERVICE_NAME="bike-ftms"

echo "=========================================="
echo "  Bike FTMS Bridge 安装脚本"
echo "=========================================="
echo ""
echo "安装目录: $SCRIPT_DIR"
echo "运行用户: $CURRENT_USER"
echo ""

if [ ! -f "$SCRIPT_DIR/identity.json" ]; then
    echo "[错误] 未找到 identity.json 鉴权配置文件！"
    echo ""
    echo "请先完成以下步骤："
    echo "1. 在安卓手机上启用蓝牙HCI日志"
    echo "2. 使用动感单车App连接单车"
    echo "3. 提取HCI日志文件（通常为btsnoop_hci.log）"
    echo "4. 运行: python identity_gen.py btsnoop_hci.log"
    echo ""
    echo "完成后再执行本安装脚本。"
    exit 1
fi

echo "[√] 已找到 identity.json"
echo ""

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "[*] 创建虚拟环境..."
    python3 -m venv "$SCRIPT_DIR/venv"
    if [ $? -ne 0 ]; then
        echo "[错误] 创建虚拟环境失败"
        exit 1
    fi
fi

echo "[*] 安装依赖..."
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
if [ $? -ne 0 ]; then
    echo "[错误] 安装依赖失败"
    exit 1
fi

echo "[√] 依赖安装完成"
echo ""

cat > "$SCRIPT_DIR/bike-ftms.service" << EOF
[Unit]
Description=Bike FTMS Server
After=network.target bluetooth.target
Wants=bluetooth.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin"
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/ftms_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "[√] 已生成 bike-ftms.service"
echo ""

echo "[*] 配置蓝牙权限..."
sudo setcap cap_net_raw,cap_net_admin+eip "$SCRIPT_DIR/venv/bin/python3" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "[√] 蓝牙权限配置成功"
else
    echo "[警告] 蓝牙权限配置失败，可能需要手动配置"
fi
echo ""

echo "=========================================="
echo "  安装完成！"
echo "=========================================="
echo ""
echo "请执行以下命令启用服务："
echo ""
echo "  sudo cp $SCRIPT_DIR/bike-ftms.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable bike-ftms.service"
echo "  sudo systemctl start bike-ftms.service"
echo ""
echo "查看服务状态："
echo "  sudo systemctl status bike-ftms.service"
echo ""
echo "查看日志："
echo "  journalctl -u bike-ftms.service -f"
echo ""
