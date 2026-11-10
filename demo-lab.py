#!/usr/bin/env python3
import os
import sys
import string
import secrets
import subprocess
from pathlib import Path

# Защита от UnicodeDecodeError в веб-консоли Proxmox
if sys.version_info >= (3, 7):
    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CACHE_DIR = Path("/var/lib/vz/demo-images")
INTERFACES_FILE = Path("/etc/network/interfaces")
CREDS_FILE = Path("/root/students_credentials.txt")

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

# Цветные теги (кружочки-закладки в Proxmox)
TAGS_MAP = {
    "ISP": "router",
    "HQ-RTR": "router",
    "HQ-SW": "switch",
    "HQ-SRV": "server",
    "HQ-CLI": "client",
    "BR-RTR": "router",
    "BR-FW": "firewall",
    "BR-SRV": "server"
}

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
    except Exception:
        pass

def download_images(profile="base"):
    fix_dns()
    target_dir = CACHE_DIR if profile == "base" else CACHE_DIR / "module2"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Проверяем, есть ли уже все образы
    all_present = True
    for filename in IMAGES[profile].keys():
        fpath = target_dir / filename
        if not fpath.exists() or fpath.stat().st_size <= 1024:
            all_present = False
            break
            
    if all_present:
        print(f"[*] Все образы {profile} уже присутствуют в кэше!")
        return

    venv_dir = Path("/root/.demo-venv")
    if not (venv_dir / "bin" / "gdown").exists():
        print("[*] Установка зависимостей (python3-venv, gdown)...")
        run("apt-get update -qq && apt-get install -y -qq python3-venv curl")
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
            cmd = f"{gdown_bin} --continue --retries 3 {file_id} -O {file_path}"
            res = run(cmd, check=False)
            # Если gdown заблокирован Google по квоте — качаем через curl с confirm=t
            if res.returncode != 0 or not file_path.exists() or file_path.stat().st_size <= 1024:
                print(f"  [*] Прямое скачивание {filename} через curl...")
                c_file = "/tmp/g_cookie.txt"
                run(f"curl -c {c_file} -s -L 'https://drive.google.com/uc?id={file_id}&export=download' > /dev/null")
                run_live(f"curl -b {c_file} -C - -L 'https://drive.usercontent.google.com/download?id={file_id}&confirm=t' -o {file_path}")
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
    
    label = "Стенд А (Модуль 1)" if profile == "base" else "Стенд В (Модуль 2)"
    print(f"\n=======================================================")
    print(f" СОЗДАНИЕ ЭТАЛОННЫХ ШАБЛОНОВ: {label}")
    print(f" Диапазон VMID шаблонов: {base_tpl_id} – {base_tpl_id + 7}")
    print(f"=======================================================")
    
    download_images(profile)
    
    if profile == "base":
        vm_configs = [
            {"name": "tpl-A-ISP",    "ram": 1024, "cpu": 1, "img": "alt-jeos.qcow2",        "type": "jeos",      "net_count": 3},
            {"name": "tpl-A-HQ-RTR", "ram": 2048, "cpu": 2, "img": "EcoRouterOS.qcow2",     "type": "router",    "net_count": 3},
            {"name": "tpl-A-HQ-SW",  "ram": 1024, "cpu": 1, "img": "alt-jeos.qcow2",        "type": "jeos",      "net_count": 3},
            {"name": "tpl-A-HQ-SRV", "ram": 2048, "cpu": 1, "img": "alt-server.qcow2",      "type": "server",    "net_count": 1},
            {"name": "tpl-A-HQ-CLI", "ram": 2048, "cpu": 2, "img": "alt-workstation.qcow2", "type": "cli",       "net_count": 1},
            {"name": "tpl-A-BR-RTR", "ram": 2048, "cpu": 2, "img": "EcoRouterOS.qcow2",     "type": "router",    "net_count": 3},
            {"name": "tpl-A-BR-FW",  "ram": 6144, "cpu": 4, "img": "ideco.qcow2",           "type": "ideco",     "net_count": 2},
            {"name": "tpl-A-BR-SRV", "ram": 2048, "cpu": 1, "img": "alt-server.qcow2",      "type": "server",    "net_count": 1},
        ]
    else:
        vm_configs = [
            {"name": "tpl-B-ISP",    "ram": 1024, "cpu": 1, "img": "isp.qcow2",     "type": "jeos",      "net_count": 3},
            {"name": "tpl-B-HQ-RTR", "ram": 2048, "cpu": 2, "img": "hq-rtr.qcow2",  "type": "router_m2", "net_count": 3},
            {"name": "tpl-B-HQ-SW",  "ram": 1024, "cpu": 1, "img": "hq-sw.qcow2",   "type": "jeos",      "net_count": 3},
            {"name": "tpl-B-HQ-SRV", "ram": 2048, "cpu": 1, "img": "hq-srv.qcow2",  "type": "server",    "net_count": 1},
            {"name": "tpl-B-HQ-CLI", "ram": 2048, "cpu": 2, "img": "hq-cli.qcow2",  "type": "cli",       "net_count": 1},
            {"name": "tpl-B-BR-RTR", "ram": 2048, "cpu": 2, "img": "br-rtr.qcow2",  "type": "router_m2", "net_count": 3},
            {"name": "tpl-B-BR-FW",  "ram": 6144, "cpu": 4, "img": "br-fw.qcow2",   "type": "ideco_m2",  "net_count": 2},
            {"name": "tpl-B-BR-SRV", "ram": 2048, "cpu": 1, "img": "br-srv.qcow2",  "type": "server",    "net_count": 1},
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

def setup_user_and_pool(student_id, mod_letter, password):
    user = f"student{student_id:02d}-{mod_letter}@pve"
    pool = f"DE_09.02.06-2027_stand_{mod_letter}-{student_id}"
    comment = f'Стенд участника демэкзамена "Сетевое и системное администрирование" {mod_letter}-{student_id}'
    run(f"pveum pool add '{pool}' --comment '{comment}'", check=False)
    run(f"pveum user add '{user}' --password '{password}' --comment 'Студент {student_id:02d} (Стенд {mod_letter})'", check=False)
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
            block = f"\n# demo-lab student {student_id:02d} (Stand {prefix})\nauto {b}\niface {b} inet manual\n    bridge-ports none\n    bridge-stp off\n    bridge-fd 0\n"
            new_blocks.append(block)
    
    if new_blocks:
        with open(INTERFACES_FILE, "a") as f:
            f.writelines(new_blocks)
        for b in bridges:
            run(f"ifup {b}", check=False)
            
    return bridges

def deploy_single_module(student_id, mod_num, storage="local-lvm"):
    # mod_num: 1 (Стенд А) или 2 (Стенд B)
    mod_letter = "A" if mod_num == 1 else "B"
    tpl_base = 900 if mod_num == 1 else 910
    mod_name = f"Стенд {mod_letter} (Модуль {mod_num})"
    
    chk = run(f"qm status {tpl_base}", check=False)
    if chk.returncode != 0:
        print(f"[!] ОШИБКА: Шаблоны для {mod_name} (VMID {tpl_base}) не найдены! Сначала создайте шаблоны через Пункт 1.")
        return False

    password = generate_password()
    user, pool = setup_user_and_pool(student_id, mod_letter, password)
    br = setup_student_bridges(student_id, prefix=str(mod_num))
    uplink = "vmbr0"
    
    print(f"\n=======================================================")
    print(f" [>] Развертывание: {mod_name} для Студента {student_id:02d}")
    print(f" Пул: {pool}")
    print(f" Логин: {user} | Пароль: {password}")
    print(f" Диапазон VMID: {mod_num}{student_id:02d}01 – {mod_num}{student_id:02d}08")
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
        vmid = int(f"{mod_num}{student_id:02d}{idx+1:02d}")
        tag = TAGS_MAP.get(role, "server")
        print(f"  * Клонирование {role} (ID {vmid}) в пул {pool}...")
        
        run(f"qm stop {vmid} --skiplock 1", check=False)
        run(f"qm destroy {vmid} --purge 1 --skiplock 1", check=False)
        
        run(f"qm clone {tpl_id} {vmid} --name '{role}' --pool '{pool}' --description '{mod_name} студента {student_id:02d}'")
        
        # Навешиваем тег для цветного кружочка (закладки) в Proxmox
        run(f"qm set {vmid} --tags '{tag}'", check=False)
        
        net_model = "e1000" if role in ["HQ-RTR", "BR-RTR"] else "virtio"
        for net_idx, bridge in enumerate(network_map[idx]):
            run(f"qm set {vmid} --net{net_idx} {net_model},bridge={bridge},firewall=0")
            
        if mod_num == 2 and role == "HQ-SRV":
            print(f"    - Добавление двух дисков по 1ГБ для RAID (стр. 52 КИМ)...")
            run(f"qm set {vmid} --scsi1 {storage}:1", check=False)
            run(f"qm set {vmid} --scsi2 {storage}:1", check=False)

        run(f"qm snapshot {vmid} lab-initial --vmstate 0 --description 'Чистый стенд'")

    cred_entry = (
        f"Студент {student_id:02d} | Стенд {mod_letter} | Логин: {user} | Пароль: {password} | Пул: {pool} | VMID: {mod_num}{student_id:02d}01..{mod_num}{student_id:02d}08\n"
    )
    with open(CREDS_FILE, "a") as f:
        f.write(cred_entry)

    print(f"[✓] {mod_name} для Студента {student_id:02d} успешно готов!\n")
    return True

def deploy_student_stands(student_id, mod_choice="all", storage="local-lvm"):
    if mod_choice in ["1", "A", "a", "all"]:
        deploy_single_module(student_id, 1, storage)
    if mod_choice in ["2", "B", "b", "all"]:
        deploy_single_module(student_id, 2, storage)

def take_snapshots(student_id, mod_choice="all", snap_name="lab-initial"):
    vmids = []
    if mod_choice in ["1", "A", "a", "all"]:
        vmids.extend([int(f"1{student_id:02d}{i+1:02d}") for i in range(8)])
    if mod_choice in ["2", "B", "b", "all"]:
        vmids.extend([int(f"2{student_id:02d}{i+1:02d}") for i in range(8)])
        
    print(f"[*] Создание снимка '{snap_name}' для Студента {student_id:02d}...")
    for vmid in vmids:
        run(f"qm delsnapshot {vmid} {snap_name}", check=False)
        run(f"qm snapshot {vmid} {snap_name} --vmstate 0 --description 'Контрольный снимок'")
    print(f"[✓] Снимки созданы!")

def reset_student_stand(student_id, mod_choice="all", snap_name="lab-initial"):
    vmids = []
    if mod_choice in ["1", "A", "a", "all"]:
        vmids.extend([int(f"1{student_id:02d}{i+1:02d}") for i in range(8)])
    if mod_choice in ["2", "B", "b", "all"]:
        vmids.extend([int(f"2{student_id:02d}{i+1:02d}") for i in range(8)])
        
    print(f"[*] Сброс стенда Студента {student_id:02d} к снимку '{snap_name}'...")
    for vmid in vmids:
        run(f"qm stop {vmid} --skiplock 1", check=False)
        run(f"qm rollback {vmid} {snap_name}", check=False)
    print(f"[✓] Сброс завершен!")

def delete_student_stand(student_id, mod_choice="all"):
    mods_to_del = []
    if mod_choice in ["1", "A", "a", "all"]:
        mods_to_del.append((1, "A"))
    if mod_choice in ["2", "B", "b", "all"]:
        mods_to_del.append((2, "B"))
        
    for m_num, m_letter in mods_to_del:
        pool = f"DE_09.02.06-2027_stand_{m_letter}-{student_id}"
        user = f"student{student_id:02d}-{m_letter}@pve"
        print(f"[*] Удаление Стенда {m_letter} Студента {student_id:02d}...")
        for i in range(8):
            vmid = int(f"{m_num}{student_id:02d}{i+1:02d}")
            run(f"qm stop {vmid} --skiplock 1", check=False)
            run(f"qm destroy {vmid} --purge 1 --skiplock 1", check=False)
        run(f"pveum pool delete '{pool}'", check=False)
        run(f"pveum user delete '{user}'", check=False)
    print(f"[✓] Удаление для студента {student_id:02d} завершено!")

def power_all_stands(start_id, end_id, mod_choice="all", action="stop"):
    print(f"[*] Команда '{action}' для студентов с {start_id:02d} по {end_id:02d}...")
    for s in range(start_id, end_id + 1):
        vmids = []
        if mod_choice in ["1", "A", "a", "all"]:
            vmids.extend([int(f"1{s:02d}{i+1:02d}") for i in range(8)])
        if mod_choice in ["2", "B", "b", "all"]:
            vmids.extend([int(f"2{s:02d}{i+1:02d}") for i in range(8)])
        for vmid in vmids:
            run(f"qm {action} {vmid}", check=False)
    print(f"[✓] Команда {action} отправлена!")

def main_menu():
    while True:
        print("\n" + "="*65)
        print("    УПРАВЛЕНИЕ СТЕНДАМИ ДЕМОЭКЗАМЕНА (КИМ 09.02.06-1-2027)")
        print("         (Стенд А = Модуль 1 | Стенд B = Модуль 2)")
        print("="*65)
        print(" 1. СОЗДАТЬ/ОБНОВИТЬ ЭТАЛОННЫЕ ШАБЛОНЫ (900-907 / 910-917)")
        print(" 2. Развернуть стенды для ОДНОГО студента (Стенд А / B / Оба)")
        print(" 3. МАССОВОЕ развертывание для группы 1-20 (А / B / Оба)")
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
        
        try:
            choice = input("Выберите пункт [0-10]: ").strip()
        except EOFError:
            break
        
        if choice == "1":
            print("\nВыберите профиль шаблонов:")
            print(" 1 - Стенд А / Модуль 1 (Базовый, чистые ОС, VMID 900-907)")
            print(" 2 - Стенд В / Модуль 2 (Преднастроенный по КИМ, VMID 910-917)")
            p = input("Профиль [1/2]: ").strip()
            create_admin_templates("module2" if p == "2" else "base")
        elif choice == "2":
            s_id = int(input("Номер студента (1-50): "))
            mod = input("Какой стенд развернуть? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            deploy_student_stands(s_id, mod)
        elif choice == "3":
            start_id = int(input("С какого студента [напр. 1]: "))
            end_id = int(input("По какого студента [напр. 20]: "))
            mod = input("Какой стенд развернуть? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            for s in range(start_id, end_id + 1):
                deploy_student_stands(s, mod)
        elif choice == "4":
            s_id = int(input("Номер студента для снимка: "))
            mod = input("Какой стенд? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            take_snapshots(s_id, mod)
        elif choice == "5":
            start_id = int(input("С какого студента: "))
            end_id = int(input("По какого студента: "))
            mod = input("Какой стенд? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            for s in range(start_id, end_id + 1):
                take_snapshots(s, mod)
        elif choice == "6":
            s_id = int(input("Номер студента: "))
            mod = input("Какой стенд сбросить? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            reset_student_stand(s_id, mod)
        elif choice == "7":
            start_id = int(input("С какого студента: "))
            end_id = int(input("По какого студента: "))
            mod = input("Какой стенд сбросить? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            for s in range(start_id, end_id + 1):
                reset_student_stand(s, mod)
        elif choice == "8":
            start_id = int(input("С какого студента: "))
            end_id = int(input("По какого студента: "))
            mod = input("Какой стенд выключить? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
            power_all_stands(start_id, end_id, mod, "stop")
        elif choice == "9":
            s_id = int(input("Номер студента для удаления: "))
            mod = input("Что удалить? 1 - Стенд А, 2 - Стенд B, all - Оба [all]: ").strip() or "all"
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
