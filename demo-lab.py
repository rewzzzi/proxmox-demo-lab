#!/usr/bin/env python3
import os
import sys
import string
import secrets
import subprocess
from pathlib import Path

CACHE_DIR = Path("/var/lib/vz/demo-images")
INTERFACES_FILE = Path("/etc/network/interfaces")
CREDS_FILE = Path("/root/students_credentials.txt")

# Google Drive ID для образов
# Модуль 1: чистые базовые диски
# Модуль 2: преднастроенные по спецификации КИМ 09.02.06-1-2027 (стр. 51-52)
IMAGES = {
    "base": {
        "alt-jeos.qcow2": "1C9enJgehyHtHXaS24YbetS15XcBRw828",
        "alt-server.qcow2": "1Rbcs3KTGyPzcv03XI1-JRqbwUXVZOMpB",
        "alt-workstation.qcow2": "1r1-1T-cfWedwYU8Vmhbg_fpy0QxGXOXh",
        "EcoRouterOS.qcow2": "1d8ykWXbxdWnKJL6k5TdmUIVxckrgBlsL",
        "ideco.qcow2": "11ynfw3ZC8HlGiYDC1HgJ6FswQQ53v_6g",
        "ideco-efi.qcow2": "11ymr6_LWPgYvcCet9iuB3itVQxNcaalI",
    },
    "module2": {
        "isp.qcow2": "1mGSZ-PPvKYMyLZrqtZhoJ4KOOM_-4hBE",
        "hq-rtr.qcow2": "1JF1SSW0bBVClHjNXKliabzq0CDb9wpEO",
        "hq-sw.qcow2": "1tlHkjRTDXGWohfUTU4Ez_w1nHSHWhGrb",
        "hq-srv.qcow2": "1YA17aln4ZrlbUAN4Y3nZp_sSEOInmBoh",
        "hq-cli.qcow2": "1RQN6brGwaNSU0jUhBuBhplL9XIgojtFk",
        "br-rtr.qcow2": "19i42EyiGHUmA2ftifSqEB8qb8AO_tj36",
        "br-fw.qcow2": "1GNaKKbCZozZdpGb8IiU_xeORaRAfKuZk",
        "br-fw-efi.qcow2": "1E0xzLjloT0LaQz8ykzRG_iaizvdXtycX",
        "br-srv.qcow2": "1B-vYLNg8Qqwje4KZ9M1qL7G8rTxOXr8H",
    }
}

ROLES = ["ISP", "HQ-RTR", "HQ-SW", "HQ-SRV", "HQ-CLI", "BR-RTR", "BR-FW", "BR-SRV"]

def run(cmd, check=True):
    res = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and res.returncode != 0:
        raise subprocess.CalledProcessError(res.returncode, cmd, res.stdout, res.stderr)
    return res

def run_live(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in iter(p.stdout.readline, ''):
        print(line, end='', flush=True)
    p.stdout.close()
    if p.wait() != 0:
        raise subprocess.CalledProcessError(p.returncode, cmd)

def generate_password(length=10):
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def fix_dns():
    try:
        resolv_path = Path("/etc/resolv.conf")
        content = ""
        if resolv_path.exists():
            content = resolv_path.read_text()
        if "77.88.8.8" not in content or "8.8.8.8" not in content:
            new_resolv = "nameserver 77.88.8.8\nnameserver 8.8.8.8\nnameserver 1.1.1.1\n"
            resolv_path.write_text(new_resolv)
    except Exception as e:
        print(f"[!] Предупреждение проверки DNS: {e}")

def download_images(profile="base"):
    fix_dns()
    target_dir = CACHE_DIR if profile == "base" else CACHE_DIR / "module2"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    venv_dir = Path("/root/.demo-venv")
    if not (venv_dir / "bin" / "gdown").exists():
        print("[*] Установка зависимостей (python3-venv, gdown)...")
        run("apt-get update -qq && apt-get install -y -qq python3-venv")
        run(f"python3 -m venv {venv_dir}")
        run(f"{venv_dir}/bin/pip install -q --upgrade 'gdown>=5.0.0'")

    gdown_bin = venv_dir / "bin" / "gdown"
    
    print(f"\n[*] Проверка и скачивание образов ({profile})...")
    for filename, file_id in IMAGES[profile].items():
        file_path = target_dir / filename
        if file_path.exists() and file_path.stat().st_size > 1024:
            print(f"  [+] Уже есть в кэше: {filename}")
        else:
            print(f"  [>] Скачивание: {filename}...")
            # gdown 5.x: аргумент ID передается без флага --id
            cmd = f"{gdown_bin} --continue --retries 5 {file_id} -O {file_path}"
            run_live(cmd)
    print("[*] Образы готовы к использованию!\n")

def get_unused_volume(vmid):
    res = run(f"qm config {vmid}")
    for line in res.stdout.splitlines():
        if line.startswith("unused0:"):
            return line.split()[1].split(",")[0]
    return None

def create_admin_templates(profile="base", storage="local-lvm"):
    base_tpl_id = 900 if profile == "base" else 910
    target_dir = CACHE_DIR if profile == "base" else CACHE_DIR / "module2"
    
    label = "Модуль 1 (Базовый чистый)" if profile == "base" else "Модуль 2 (Преднастроенный по КИМ)"
    print(f"\n=======================================================")
    print(f" СОЗДАНИЕ ЭТАЛОННЫХ ШАБЛОНОВ: {label}")
    print(f" Диапазон VMID шаблонов: {base_tpl_id} – {base_tpl_id + 7}")
    print(f"=======================================================")
    
    download_images(profile)
    
    if profile == "base":
        vm_configs = [
            {"name": "tpl-M1-ISP",    "ram": 1024, "cpu": 1, "img": "alt-jeos.qcow2",        "type": "jeos",      "net_count": 3},
            {"name": "tpl-M1-HQ-RTR", "ram": 2048, "cpu": 2, "img": "EcoRouterOS.qcow2",     "type": "router",    "net_count": 3},
            {"name": "tpl-M1-HQ-SW",  "ram": 1024, "cpu": 1, "img": "alt-jeos.qcow2",        "type": "jeos",      "net_count": 3},
            {"name": "tpl-M1-HQ-SRV", "ram": 2048, "cpu": 1, "img": "alt-server.qcow2",      "type": "server",    "net_count": 1},
            {"name": "tpl-M1-HQ-CLI", "ram": 2048, "cpu": 2, "img": "alt-workstation.qcow2", "type": "cli",       "net_count": 1},
            {"name": "tpl-M1-BR-RTR", "ram": 2048, "cpu": 2, "img": "EcoRouterOS.qcow2",     "type": "router",    "net_count": 3},
            {"name": "tpl-M1-BR-FW",  "ram": 6144, "cpu": 4, "img": "ideco.qcow2",           "type": "ideco",     "net_count": 2},
            {"name": "tpl-M1-BR-SRV", "ram": 2048, "cpu": 1, "img": "alt-server.qcow2",      "type": "server",    "net_count": 1},
        ]
    else:
        vm_configs = [
            {"name": "tpl-M2-ISP",    "ram": 1024, "cpu": 1, "img": "isp.qcow2",     "type": "jeos",      "net_count": 3},
            {"name": "tpl-M2-HQ-RTR", "ram": 2048, "cpu": 2, "img": "hq-rtr.qcow2",  "type": "router_m2", "net_count": 3},
            {"name": "tpl-M2-HQ-SW",  "ram": 1024, "cpu": 1, "img": "hq-sw.qcow2",   "type": "jeos",      "net_count": 3},
            {"name": "tpl-M2-HQ-SRV", "ram": 2048, "cpu": 1, "img": "hq-srv.qcow2",  "type": "server",    "net_count": 1},
            {"name": "tpl-M2-HQ-CLI", "ram": 2048, "cpu": 2, "img": "hq-cli.qcow2",  "type": "cli",       "net_count": 1},
            {"name": "tpl-M2-BR-RTR", "ram": 2048, "cpu": 2, "img": "br-rtr.qcow2",  "type": "router_m2", "net_count": 3},
            {"name": "tpl-M2-BR-FW",  "ram": 6144, "cpu": 4, "img": "br-fw.qcow2",   "type": "ideco_m2",  "net_count": 2},
            {"name": "tpl-M2-BR-SRV", "ram": 2048, "cpu": 1, "img": "br-srv.qcow2",  "type": "server",    "net_count": 1},
        ]

    for idx, cfg in enumerate(vm_configs):
        vmid = base_tpl_id + idx
        name = cfg["name"]
        
        cfg_check = run(f"qm config {vmid}", check=False)
        if cfg_check.returncode == 0 and "template: 1" in cfg_check.stdout:
            print(f"[*] [{idx+1}/8] Шаблон {vmid} ({name}) УЖЕ ГОТОВ, пропускаем!")
            continue

        print(f"\n[*] [{idx+1}/8] Создание шаблона {vmid} ({name})...")
        
        run(f"qm stop {vmid} --skiplock 1", check=False)
        run(f"qm destroy {vmid} --purge 1 --skiplock 1", check=False)
        
        run(f"qm create {vmid} --name '{name}' --memory {cfg['ram']} --balloon 0 --cores {cfg['cpu']} "
            f"--cpu host --ostype l26 --onboot 0 --description 'Template Demo Lab'")
        
        net_model = "e1000" if cfg["type"] in ["router", "router_m2"] else "virtio"
        for net_idx in range(cfg["net_count"]):
            run(f"qm set {vmid} --net{net_idx} {net_model},bridge=vmbr0,firewall=0")
            
        img_path = target_dir / cfg["img"]
        print(f"    - Импорт диска {cfg['img']} (прогресс распаковки):")
        run_live(f"qm importdisk {vmid} {img_path} {storage}")
        vol = get_unused_volume(vmid)
        
        if cfg["type"] == "router":
            run(f"qm set {vmid} --sata0 {vol} --boot order=sata0")
            run(f"qm resize {vmid} sata0 10G", check=False)
        elif cfg["type"] == "router_m2":
            run(f"qm set {vmid} --ide0 {vol} --boot order=ide0")
        elif cfg["type"] == "ideco":
            run(f"qm set {vmid} --bios ovmf --machine q35 --scsihw virtio-scsi-single --scsi0 {vol},iothread=1 --boot order=scsi0")
            efi_path = target_dir / "ideco-efi.qcow2"
            print("    - Импорт EFI-диска:")
            run_live(f"qm importdisk {vmid} {efi_path} {storage}")
            efi_vol = get_unused_volume(vmid)
            run(f"qm set {vmid} --efidisk0 {efi_vol},efitype=4m,pre-enrolled-keys=0")
        elif cfg["type"] == "ideco_m2":
            run(f"qm set {vmid} --bios ovmf --machine pc --scsihw virtio-scsi-single --ide0 {vol} --boot order=ide0")
            efi_path = target_dir / "br-fw-efi.qcow2"
            print("    - Импорт EFI-диска:")
            run_live(f"qm importdisk {vmid} {efi_path} {storage}")
            efi_vol = get_unused_volume(vmid)
            run(f"qm set {vmid} --efidisk0 {efi_vol},efitype=4m,pre-enrolled-keys=0")
        else:
            run(f"qm set {vmid} --bios seabios --scsihw virtio-scsi-single --scsi0 {vol},iothread=1 --serial0 socket --boot order=scsi0")

        print(f"    - Конвертация в шаблон (qm template)...")
        run(f"qm template {vmid}")

    print(f"\n[✓] Все 8 эталонных шаблонов готовы (VMID {base_tpl_id}–{base_tpl_id+7})!\n")

def setup_user_and_pool(student_id, module_key, password):
    user = f"student{student_id:02d}-{module_key}@pve"
    pool = f"pool-student-{student_id:02d}-{module_key}"
    run(f"pveum pool add {pool} --comment 'Lab Stand {module_key.upper()} for Student {student_id:02d}'", check=False)
    run(f"pveum user add {user} --password '{password}' --comment 'Student {student_id:02d} ({module_key.upper()})'", check=False)
    run(f"pveum acl modify /pool/{pool} -user {user} -role PVEVMUser", check=False)
    return user, pool

def setup_student_bridges(student_id, prefix="1"):
    base_br = int(f"{prefix}{student_id:02d}0")
    bridges = [f"vmbr{base_br + i}" for i in range(1, 10)]
    
    with open(INTERFACES_FILE, "r") as f:
        content = f.read()

    new_blocks = []
    for b in bridges:
        if b not in content:
            block = f"\n# demo-lab student {student_id:02d} (M{prefix})\nauto {b}\niface {b} inet manual\n    bridge-ports none\n    bridge-stp off\n    bridge-fd 0\n"
            new_blocks.append(block)
    
    if new_blocks:
        with open(INTERFACES_FILE, "a") as f:
            f.writelines(new_blocks)
        for b in bridges:
            run(f"ifup {b}", check=False)
            
    return bridges

def deploy_single_module(student_id, mod_key, storage="local-lvm"):
    tpl_base = 900 if mod_key == "m1" else 910
    mod_name = "Модуль 1" if mod_key == "m1" else "Модуль 2"
    
    chk = run(f"qm status {tpl_base}", check=False)
    if chk.returncode != 0:
        print(f"[!] ОШИБКА: Шаблоны для {mod_name} (VMID {tpl_base}) не найдены! Сначала создайте шаблоны через Пункт 1.")
        return False

    password = generate_password()
    user, pool = setup_user_and_pool(student_id, mod_key, password)
    br = setup_student_bridges(student_id, prefix="1" if mod_key == "m1" else "2")
    uplink = "vmbr0"
    
    base_vmid = 200 + (student_id - 1) * 20 + (0 if mod_key == "m1" else 10)
    
    print(f"\n=======================================================")
    print(f" [>] Развертывание {mod_name} для Студента {student_id:02d}")
    print(f" Пул: {pool} | Логин: {user} | Пароль: {password}")
    print(f" Диапазон VMID: {base_vmid} – {base_vmid+7}")
    print(f"=======================================================")
    
    network_map = [
        [uplink, br[0], br[1]], # ISP
        [br[7], br[0], br[2]],  # HQ-RTR
        [br[2], br[3], br[4]],  # HQ-SW
        [br[3]],                # HQ-SRV
        [br[4]],                # HQ-CLI
        [br[8], br[1], br[5]],  # BR-RTR
        [br[6], br[5]],         # BR-FW
        [br[6]],                # BR-SRV
    ]

    for idx, role in enumerate(ROLES):
        tpl_id = tpl_base + idx
        vmid = base_vmid + idx
        print(f"  * Клонирование {role} (ID {vmid}) в {pool}...")
        
        run(f"qm stop {vmid} --skiplock 1", check=False)
        run(f"qm destroy {vmid} --purge 1 --skiplock 1", check=False)
        
        run(f"qm clone {tpl_id} {vmid} --name '{role}' --pool '{pool}' --description '{mod_name} студента {student_id:02d}'")
        
        net_model = "e1000" if role in ["HQ-RTR", "BR-RTR"] else "virtio"
        for net_idx, bridge in enumerate(network_map[idx]):
            run(f"qm set {vmid} --net{net_idx} {net_model},bridge={bridge},firewall=0")
            
        if mod_key == "m2" and role == "HQ-SRV":
            print(f"    - Добавление двух накопителей по 1ГБ для RAID (стр. 52 КИМ)...")
            run(f"qm set {vmid} --scsi1 {storage}:1", check=False)
            run(f"qm set {vmid} --scsi2 {storage}:1", check=False)

        run(f"qm snapshot {vmid} lab-initial --vmstate 0 --description 'Чистый стенд'")

    cred_entry = (
        f"Студент {student_id:02d} | {mod_name} | Логин: {user} | Пароль: {password} | Пул: {pool} | VMID: {base_vmid}..{base_vmid+7}\n"
    )
    with open(CREDS_FILE, "a") as f:
        f.write(cred_entry)

    print(f"[✓] {mod_name} для Студента {student_id:02d} успешно готов!\n")
    return True

def deploy_student_stands(student_id, mod_choice="all", storage="local-lvm"):
    if mod_choice in ["1", "all"]:
        deploy_single_module(student_id, "m1", storage)
    if mod_choice in ["2", "all"]:
        deploy_single_module(student_id, "m2", storage)

def take_snapshots(student_id, mod_choice="all", snap_name="lab-initial"):
    base_vmid = 200 + (student_id - 1) * 20
    vmids = []
    if mod_choice in ["1", "all"]:
        vmids.extend([base_vmid + i for i in range(8)])
    if mod_choice in ["2", "all"]:
        vmids.extend([base_vmid + 10 + i for i in range(8)])
        
    print(f"[*] Создание снимка '{snap_name}' для Студента {student_id:02d}...")
    for vmid in vmids:
        run(f"qm delsnapshot {vmid} {snap_name}", check=False)
        run(f"qm snapshot {vmid} {snap_name} --vmstate 0 --description 'Контрольный снимок'")
    print(f"[✓] Снимки созданы!")

def reset_student_stand(student_id, mod_choice="all", snap_name="lab-initial"):
    base_vmid = 200 + (student_id - 1) * 20
    vmids = []
    if mod_choice in ["1", "all"]:
        vmids.extend([base_vmid + i for i in range(8)])
    if mod_choice in ["2", "all"]:
        vmids.extend([base_vmid + 10 + i for i in range(8)])
        
    print(f"[*] Сброс стенда Студента {student_id:02d} к снимку '{snap_name}'...")
    for vmid in vmids:
        run(f"qm stop {vmid} --skiplock 1", check=False)
        run(f"qm rollback {vmid} {snap_name}", check=False)
    print(f"[✓] Сброс завершен!")

def delete_student_stand(student_id, mod_choice="all"):
    base_vmid = 200 + (student_id - 1) * 20
    mods_to_del = []
    if mod_choice in ["1", "all"]:
        mods_to_del.append(("m1", base_vmid))
    if mod_choice in ["2", "all"]:
        mods_to_del.append(("m2", base_vmid + 10))
        
    for k, v_start in mods_to_del:
        print(f"[*] Удаление {k.upper()} Студента {student_id:02d}...")
        for i in range(8):
            run(f"qm stop {v_start + i} --skiplock 1", check=False)
            run(f"qm destroy {v_start + i} --purge 1 --skiplock 1", check=False)
        run(f"pveum pool delete pool-student-{student_id:02d}-{k}", check=False)
        run(f"pveum user delete student{student_id:02d}-{k}@pve", check=False)
    print(f"[✓] Удаление для студента {student_id:02d} завершено!")

def power_all_stands(start_id, end_id, mod_choice="all", action="stop"):
    print(f"[*] Команда '{action}' для студентов с {start_id:02d} по {end_id:02d}...")
    for s in range(start_id, end_id + 1):
        base_vmid = 200 + (s - 1) * 20
        vmids = []
        if mod_choice in ["1", "all"]:
            vmids.extend([base_vmid + i for i in range(8)])
        if mod_choice in ["2", "all"]:
            vmids.extend([base_vmid + 10 + i for i in range(8)])
        for vmid in vmids:
            run(f"qm {action} {vmid}", check=False)
    print(f"[✓] Команда {action} отправлена!")

def main_menu():
    while True:
        print("\n" + "="*65)
        print("    УПРАВЛЕНИЕ СТЕНДАМИ ДЕМОЭКЗАМЕНА (КИМ 09.02.06-1-2027)")
        print("          (2 отдельных пула и логина на студента)")
        print("="*65)
        print(" 1. СОЗДАТЬ/ОБНОВИТЬ ЭТАЛОННЫЕ ШАБЛОНЫ (900-907 / 910-917)")
        print(" 2. Развернуть стенды для ОДНОГО студента (M1 / M2 / Оба)")
        print(" 3. МАССОВОЕ развертывание для группы 1-20 (M1 / M2 / Оба)")
        print("-" * 65)
        print(" 4. Создать контрольные снимки для ОДНОГО студента")
        print(" 5. Создать контрольные снимки МАССОВО (для группы)")
        print("-" * 65)
        print(" 6. Сбросить стенд студента к снимку (Reset)")
        print(" 7. Массовый сброс стендов группы (Reset группы)")
        print(" 8. Выключить все машины группы (Stop all)")
        print(" 9. Удалить стенды студента (ВМ, пулы, логины)")
        print("10. Показать карточки логинов и паролей (credentials.txt)")
        print(" 0. Выход")
        print("="*65)
        
        choice = input("Выберите пункт [0-10]: ").strip()
        
        if choice == "1":
            print("\nВыберите профиль шаблонов:")
            print(" 1 - Модуль 1 (Базовый, чистые ОС, VMID 900-907)")
            print(" 2 - Модуль 2 (Преднастроенный по КИМ, VMID 910-917)")
            p = input("Профиль [1/2]: ").strip()
            create_admin_templates("module2" if p == "2" else "base")
        elif choice == "2":
            s_id = int(input("Номер студента (1-50): "))
            mod = input("Какой модуль развернуть? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            deploy_student_stands(s_id, mod)
        elif choice == "3":
            start_id = int(input("С какого студента [напр. 1]: "))
            end_id = int(input("По какого студента [напр. 20]: "))
            mod = input("Какой модуль развернуть? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            for s in range(start_id, end_id + 1):
                deploy_student_stands(s, mod)
        elif choice == "4":
            s_id = int(input("Номер студента для снимка: "))
            mod = input("Какой модуль? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            take_snapshots(s_id, mod)
        elif choice == "5":
            start_id = int(input("С какого студента: "))
            end_id = int(input("По какого студента: "))
            mod = input("Какой модуль? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            for s in range(start_id, end_id + 1):
                take_snapshots(s, mod)
        elif choice == "6":
            s_id = int(input("Номер студента: "))
            mod = input("Какой модуль сбросить? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            reset_student_stand(s_id, mod)
        elif choice == "7":
            start_id = int(input("С какого студента: "))
            end_id = int(input("По какого студента: "))
            mod = input("Какой модуль сбросить? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            for s in range(start_id, end_id + 1):
                reset_student_stand(s, mod)
        elif choice == "8":
            start_id = int(input("С какого студента: "))
            end_id = int(input("По какого студента: "))
            mod = input("Какой модуль выключить? 1 - Модуль 1, 2 - Модуль 2, all - Оба [all]: ").strip() or "all"
            power_all_stands(start_id, end_id, mod, "stop")
        elif choice == "9":
            s_id = int(input("Номер студента для удаления: "))
            mod = input("Что удалить? 1 - Только Модуль 1, 2 - Только Модуль 2, all - Все [all]: ").strip() or "all"
            delete_student_stand(s_id, mod)
        elif choice == "10":
            if CREDS_FILE.exists():
                print("\n" + "="*70)
                print(" СПИСОК УЧЕТНЫХ ЗАПИСЕЙ СТУДЕНТОВ ДЕМОЭКЗАМЕНА")
                print("="*70)
                with open(CREDS_FILE) as f:
                    print(f.read())
            else:
                print("Файл учетных записей пуст.")
        elif choice == "0":
            break

if __name__ == "__main__":
    if os.geteuid() != 0:
        sys.exit("Запускайте скрипт от пользователя root!")
    main_menu()
