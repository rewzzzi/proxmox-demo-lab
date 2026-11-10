#!/usr/bin/env bash
set -e

if [ "$EUID" -ne 0 ]; then
  echo "[-] Ошибка: Запустите скрипт от пользователя root!"
  exit 1
fi

echo "[*] Подготовка окружения для стендов Демоэкзамена..."

# Настройка надежных DNS серверов
if ! grep -q "77.88.8.8" /etc/resolv.conf; then
    echo -e "nameserver 77.88.8.8\nnameserver 8.8.8.8\nnameserver 1.1.1.1" > /etc/resolv.conf
fi

apt-get update -qq
apt-get install -y -qq python3-venv git curl

INSTALL_DIR="/root/proxmox-demo-lab"

if [ ! -d "$INSTALL_DIR" ]; then
    echo "[*] Клонирование репозитория..."
    git clone https://github.com/rewzzzi/proxmox-demo-lab.git "$INSTALL_DIR"
else
    echo "[*] Обновление репозитория..."
    cd "$INSTALL_DIR" && git pull
fi

chmod +x "$INSTALL_DIR/demo-lab.py"
ln -sf "$INSTALL_DIR/demo-lab.py" /usr/local/bin/demo-lab

echo ""
echo "========================================================="
echo " [✓] Установка завершена!"
echo " Запустите менеджер стендов командой:"
echo " demo-lab"
echo "========================================================="
