#!/usr/bin/env python3
"""
Hardware Fan Management CLI Engine
----------------------------------
Command-line interface to monitor and control hardware cooling fans on Linux.
Uses the ACPI-WMI kernel driver interface (linuwu_sense).
"""

import argparse
import glob
import os
import sys
import time

SYS_FAN = "/sys/devices/platform/acer-wmi/nitro_sense/fan_speed"
PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"

def get_hwmon():
    for d in glob.glob("/sys/devices/platform/acer-wmi/hwmon/hwmon*"):
        return d
    return None

def is_driver_loaded():
    return os.path.exists(SYS_FAN)

def read_telemetry():
    hwmon = get_hwmon()
    data = {
        "driver_loaded": is_driver_loaded(),
        "fan_mode": "Unknown",
        "cpu_rpm": 0,
        "gpu_rpm": 0,
        "cpu_temp": 0,
        "gpu_temp": 0,
        "profile": "Unknown",
    }
    
    if not data["driver_loaded"]:
        return data

    try:
        with open(SYS_FAN, "r") as f:
            data["fan_mode"] = f.read().strip()
    except Exception:
        pass

    if os.path.exists(PLATFORM_PROFILE):
        try:
            with open(PLATFORM_PROFILE, "r") as f:
                data["profile"] = f.read().strip()
        except Exception:
            pass

    if hwmon:
        fan1_path = os.path.join(hwmon, "fan1_input")
        fan2_path = os.path.join(hwmon, "fan2_input")
        temp1_path = os.path.join(hwmon, "temp1_input")
        temp2_path = os.path.join(hwmon, "temp2_input")

        try:
            if os.path.exists(fan1_path):
                with open(fan1_path, "r") as f:
                    data["cpu_rpm"] = int(f.read().strip())
            if os.path.exists(fan2_path):
                with open(fan2_path, "r") as f:
                    data["gpu_rpm"] = int(f.read().strip())
            if os.path.exists(temp1_path):
                with open(temp1_path, "r") as f:
                    data["cpu_temp"] = int(f.read().strip()) // 1000
            if os.path.exists(temp2_path):
                with open(temp2_path, "r") as f:
                    data["gpu_temp"] = int(f.read().strip()) // 1000
        except Exception:
            pass

    return data

def set_fan_speed(cpu_pct: int, gpu_pct: int):
    if not is_driver_loaded():
        print("\033[0;31m[ERROR] linuwu_sense kernel module is not loaded.\033[0m")
        print("Run: sudo modprobe linuwu_sense")
        return False

    # Safety check: if non-zero custom speed is requested below 25%, clamp to 25% safe minimum
    # to prevent accidental fan motor stall under load. 0,0 remains Auto (BIOS managed).
    if 0 < cpu_pct < 25:
        print("\033[1;33m[!] Clamping CPU fan speed to safe minimum (25%) to prevent motor stall.\033[0m")
        cpu_pct = 25
    if 0 < gpu_pct < 25:
        print("\033[1;33m[!] Clamping GPU fan speed to safe minimum (25%) to prevent motor stall.\033[0m")
        gpu_pct = 25

    # Thermal Safeguard: protect user hardware against extreme heat buildup
    if cpu_pct > 0 or gpu_pct > 0:
        t = read_telemetry()
        max_t = max(t.get("cpu_temp", 0), t.get("gpu_temp", 0))
        if max_t >= 88:
            if cpu_pct < 65:
                print(f"\033[1;33m[!] Thermal Safeguard: High heat ({max_t}°C) detected. Raising CPU fan to 65%.\033[0m")
                cpu_pct = 65
            if gpu_pct < 65:
                print(f"\033[1;33m[!] Thermal Safeguard: High heat ({max_t}°C) detected. Raising GPU fan to 65%.\033[0m")
                gpu_pct = 65

    cpu_pct = max(0, min(100, int(cpu_pct)))
    gpu_pct = max(0, min(100, int(gpu_pct)))
    val = f"{cpu_pct},{gpu_pct}"

    try:
        with open(SYS_FAN, "w") as f:
            f.write(val)
        return True
    except PermissionError:
        # Fall back to pkexec / sudo tee
        cmd = f"echo '{val}' | sudo tee {SYS_FAN} > /dev/null"
        ret = os.system(cmd)
        return ret == 0
    except Exception as e:
        print(f"\033[0;31m[ERROR] Failed to set fan speed: {e}\033[0m")
        return False

def print_status():
    t = read_telemetry()
    if not t["driver_loaded"]:
        print("\033[0;31m[!] linuwu_sense driver is not active.\033[0m")
        print("Load the driver with: sudo modprobe linuwu_sense")
        sys.exit(1)

    mode_label = "Auto (BIOS Curve)"
    if t["fan_mode"] == "100,100":
        mode_label = "\033[1;31mMax Turbo (100%)\033[0m"
    elif t["fan_mode"] == "0,0":
        mode_label = "\033[1;32mAuto (Normal)\033[0m"
    else:
        mode_label = f"\033[1;34mCustom ({t['fan_mode']})\033[0m"

    print("==================================================")
    print("        \033[1;36mHardware Fan Control & Telemetry\033[0m          ")
    print("==================================================")
    print(f" Active Fan Mode:   {mode_label}")
    print(f" Platform Profile:  \033[1;33m{t['profile']}\033[0m")
    print("--------------------------------------------------")
    print(f" CPU Fan Speed:     \033[1;37m{t['cpu_rpm']:5d} RPM\033[0m")
    print(f" GPU Fan Speed:     \033[1;37m{t['gpu_rpm']:5d} RPM\033[0m")
    print("--------------------------------------------------")
    print(f" CPU Temperature:   \033[1;35m{t['cpu_temp']:3d} °C\033[0m")
    if t['gpu_temp'] > 0:
        print(f" GPU Temperature:   \033[1;35m{t['gpu_temp']:3d} °C\033[0m")
    print("==================================================")

def live_watch():
    if not is_driver_loaded():
        print("\033[0;31m[!] linuwu_sense driver is not active.\033[0m")
        sys.exit(1)

    print("\033[?25l", end="") # Hide cursor
    try:
        while True:
            os.system("clear")
            print_status()
            print("\nPress Ctrl+C to exit real-time monitoring...")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\033[?25h\nExited.")

def main():
    parser = argparse.ArgumentParser(
        description="Fan Control: Open-source Linux cooling and hardware fan manager",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    subparsers.add_parser("status", help="Show current fan speeds, modes, and temps")
    subparsers.add_parser("max", help="Force fans to 100% full blast (Turbo)")
    subparsers.add_parser("auto", help="Restore fans to automatic BIOS management")
    subparsers.add_parser("watch", help="Real-time terminal dashboard (updates every 1s)")
    subparsers.add_parser("gui", help="Launch the graphical user interface")

    set_parser = subparsers.add_parser("set", help="Set custom CPU and GPU fan percentages (safe range: 25-100)")
    set_parser.add_argument("cpu", type=int, help="CPU fan speed percentage (25-100, or 0 for auto)")
    set_parser.add_argument("gpu", type=int, nargs="?", default=None, help="GPU fan speed percentage (defaults to CPU value)")

    args = parser.parse_args()

    if args.command == "status" or args.command is None:
        print_status()
    elif args.command == "max":
        if set_fan_speed(100, 100):
            print("\033[1;32m[✓] Forced fans to MAX Turbo (100%).\033[0m")
            time.sleep(0.5)
            print_status()
    elif args.command == "auto":
        if set_fan_speed(0, 0):
            print("\033[1;32m[✓] Restored fans to AUTO (BIOS Managed Curve).\033[0m")
            time.sleep(0.5)
            print_status()
    elif args.command == "set":
        gpu_val = args.gpu if args.gpu is not None else args.cpu
        if args.cpu == 0 and gpu_val == 0:
            print("\033[1;33m[!] Note: Setting custom speed to 0% is prevented to protect hardware from motor stalling and heat.\033[0m")
            print("\033[1;32m[✓] Routing safely to AUTO mode (firmware-managed thermal curve).\033[0m")
            if set_fan_speed(0, 0):
                time.sleep(0.5)
                print_status()
        elif set_fan_speed(args.cpu, gpu_val):
            print(f"\033[1;32m[✓] Applied custom fan speed: CPU={args.cpu}%, GPU={gpu_val}%.\033[0m")
            time.sleep(0.5)
            print_status()
    elif args.command == "watch":
        live_watch()
    elif args.command == "gui":
        gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui", "nitro_gui.py")
        os.execv(sys.executable, [sys.executable, gui_path])

if __name__ == "__main__":
    main()
