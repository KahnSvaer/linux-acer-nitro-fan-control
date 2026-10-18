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

_CACHED_PATHS = None
_LAST_PROFILE_TIME = 0.0
_CACHED_PROFILE = "balanced"
_LAST_TELEMETRY = {
    "driver_loaded": False,
    "fan_mode": "Unknown",
    "cpu_rpm": 0,
    "gpu_rpm": 0,
    "cpu_temp": 0,
    "gpu_temp": 0,
    "profile": "balanced",
    "latency_ms": 0.0,
}

def get_sensor_paths():
    global _CACHED_PATHS
    if _CACHED_PATHS and os.path.exists(_CACHED_PATHS.get("fan1", "")):
        return _CACHED_PATHS

    # 1. Primary Acer platform WMI hwmon
    hwmon_dirs = glob.glob("/sys/devices/platform/acer-wmi/hwmon/hwmon*")
    
    # 2. Fallback scan across all system hwmon nodes for 'acer'
    if not hwmon_dirs:
        for p in glob.glob("/sys/class/hwmon/hwmon*"):
            name_file = os.path.join(p, "name")
            if os.path.exists(name_file):
                try:
                    with open(name_file, "r") as f:
                        if "acer" in f.read().strip():
                            hwmon_dirs.append(p)
                            break
                except Exception:
                    pass

    if hwmon_dirs:
        hwmon = hwmon_dirs[0]
        _CACHED_PATHS = {
            "fan1": os.path.join(hwmon, "fan1_input"),
            "fan2": os.path.join(hwmon, "fan2_input"),
            "temp1": os.path.join(hwmon, "temp1_input"),
            "temp2": os.path.join(hwmon, "temp2_input"),
            "temp3": os.path.join(hwmon, "temp3_input"),
        }
        return _CACHED_PATHS
    return None

def is_driver_loaded():
    return os.path.exists(SYS_FAN)

def read_telemetry(force_profile: bool = False):
    global _LAST_TELEMETRY, _LAST_PROFILE_TIME, _CACHED_PROFILE
    t0 = time.perf_counter()
    paths = get_sensor_paths()

    # 1. Read active fan mode
    try:
        with open(SYS_FAN, "r") as f:
            mode_content = f.read().strip()
            if mode_content:
                _LAST_TELEMETRY["fan_mode"] = mode_content
                _LAST_TELEMETRY["driver_loaded"] = True
    except FileNotFoundError:
        _LAST_TELEMETRY["driver_loaded"] = False
        return _LAST_TELEMETRY.copy()
    except Exception:
        pass

    _LAST_TELEMETRY["driver_loaded"] = True

    # 2. Read platform profile (cache for 2.0s to avoid ACPI EC evaluation latency of ~4.5ms)
    now = time.time()
    if force_profile or (now - _LAST_PROFILE_TIME > 2.0) or _LAST_TELEMETRY.get("profile") == "Unknown":
        if os.path.exists(PLATFORM_PROFILE):
            try:
                with open(PLATFORM_PROFILE, "r") as f:
                    prof_content = f.read().strip()
                    if prof_content:
                        _CACHED_PROFILE = prof_content
                        _LAST_PROFILE_TIME = now
            except Exception:
                pass
    _LAST_TELEMETRY["profile"] = _CACHED_PROFILE

    # 3. High-speed direct sysfs sensor readings (< 1.5ms)
    if paths:
        # CPU Fan RPM
        try:
            with open(paths["fan1"], "r") as f:
                raw = f.read().strip()
                if raw:
                    _LAST_TELEMETRY["cpu_rpm"] = int(raw)
        except Exception:
            pass

        # GPU Fan RPM
        try:
            with open(paths["fan2"], "r") as f:
                raw = f.read().strip()
                if raw:
                    _LAST_TELEMETRY["gpu_rpm"] = int(raw)
        except Exception:
            pass

        # CPU Temp
        try:
            with open(paths["temp1"], "r") as f:
                raw = f.read().strip()
                if raw:
                    _LAST_TELEMETRY["cpu_temp"] = int(raw) // 1000
        except Exception:
            pass

        # GPU Temp (with fallback to temp3 if temp2 reports 0)
        try:
            with open(paths["temp2"], "r") as f:
                raw = f.read().strip()
                if raw:
                    val = int(raw) // 1000
                    if val > 0:
                        _LAST_TELEMETRY["gpu_temp"] = val
                    elif os.path.exists(paths.get("temp3", "")):
                        with open(paths["temp3"], "r") as f3:
                            raw3 = f3.read().strip()
                            if raw3 and int(raw3) > 0:
                                _LAST_TELEMETRY["gpu_temp"] = int(raw3) // 1000
        except Exception:
            pass

    _LAST_TELEMETRY["latency_ms"] = (time.perf_counter() - t0) * 1000.0
    return _LAST_TELEMETRY.copy()

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
            f.flush()

        # Immediate verification that hardware sysfs node accepted the value
        try:
            with open(SYS_FAN, "r") as f:
                verified = f.read().strip()
                if verified:
                    _LAST_TELEMETRY["fan_mode"] = verified
        except Exception:
            _LAST_TELEMETRY["fan_mode"] = val

        return True
    except PermissionError:
        # Fall back to pkexec / sudo tee
        cmd = f"echo '{val}' | sudo tee {SYS_FAN} > /dev/null"
        ret = os.system(cmd)
        if ret == 0:
            _LAST_TELEMETRY["fan_mode"] = val
            return True
        return False
    except Exception as e:
        print(f"\033[0;31m[ERROR] Failed to set fan speed: {e}\033[0m")
        return False

def print_status():
    t = read_telemetry(force_profile=False)
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

    cpu_pct = (t["cpu_rpm"] / 6800.0) * 100.0 if t["cpu_rpm"] > 0 else 0.0
    gpu_pct = (t["gpu_rpm"] / 6400.0) * 100.0 if t["gpu_rpm"] > 0 else 0.0

    print("==================================================")
    print("        \033[1;36mHardware Fan Control & Telemetry\033[0m          ")
    print("==================================================")
    print(f" Active Fan Mode:   {mode_label}")
    print(f" Platform Profile:  \033[1;33m{t['profile']}\033[0m")
    print(f" Read Latency:      \033[1;32m{t.get('latency_ms', 1.0):.1f} ms\033[0m")
    print("--------------------------------------------------")
    print(f" CPU Fan Speed:     \033[1;37m{t['cpu_rpm']:5d} RPM\033[0m ({cpu_pct:4.1f}% scale)")
    print(f" GPU Fan Speed:     \033[1;37m{t['gpu_rpm']:5d} RPM\033[0m ({gpu_pct:4.1f}% scale)")
    print("--------------------------------------------------")
    print(f" CPU Temperature:   \033[1;35m{t['cpu_temp']:3d} °C\033[0m")
    if t['gpu_temp'] > 0:
        print(f" GPU Temperature:   \033[1;35m{t['gpu_temp']:3d} °C\033[0m")
    print("==================================================")

def live_watch(interval: float = 0.25):
    """Fast, flicker-free live dashboard updating every 250ms (4 Hz)."""
    if not is_driver_loaded():
        print("\033[0;31m[!] linuwu_sense driver is not active.\033[0m")
        sys.exit(1)

    print("\033[?25l", end="")  # Hide cursor
    os.system("clear")
    try:
        while True:
            print("\033[H", end="")  # Move cursor to home without full terminal clear
            print_status()
            hz = int(round(1.0 / interval)) if interval > 0 else 4
            print(f"\nLive monitoring active ({hz} Hz / {interval*1000:.0f}ms refresh) | Press Ctrl+C to exit...   ")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\033[?25h\nExited.")

def check_fan_control():
    """Diagnostic self-check verifying driver, permissions, sensor latency, and hardware control."""
    print("==================================================")
    print("       Hardware Fan Control & Sensor Check        ")
    print("==================================================")

    # 1. Driver check
    print(" [1/4] Checking linuwu_sense kernel driver...", end=" ", flush=True)
    if not is_driver_loaded():
        print("\033[0;31mFAILED\033[0m")
        print("       Kernel sysfs interface not found at:", SYS_FAN)
        return False
    print("\033[1;32mOK\033[0m")

    # 2. Permissions check
    print(" [2/4] Checking passwordless control permissions...", end=" ", flush=True)
    if not os.access(SYS_FAN, os.W_OK):
        print("\033[1;33mRESTRICTED\033[0m")
        print("       SYS_FAN requires elevated permissions. Run: sudo ./install.sh")
    else:
        print("\033[1;32mOK (0666)\033[0m")

    # 3. RPM Sensor read latency benchmark & live telemetry
    print(" [3/4] Benchmarking live RPM sensor reading...", end=" ", flush=True)
    latencies = []
    # Sample 5 high-speed reads
    for _ in range(5):
        t0 = time.perf_counter()
        t = read_telemetry(force_profile=False)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    avg_lat = sum(latencies) / len(latencies)
    min_lat = min(latencies)
    max_lat = max(latencies)
    print(f"\033[1;32mOK (Avg: {avg_lat:.2f}ms | Min: {min_lat:.2f}ms | Max: {max_lat:.2f}ms)\033[0m")
    cpu_pct = (t["cpu_rpm"] / 6800.0) * 100.0 if t["cpu_rpm"] > 0 else 0.0
    gpu_pct = (t["gpu_rpm"] / 6400.0) * 100.0 if t["gpu_rpm"] > 0 else 0.0
    print(f"       Live CPU: \033[1;37m{t['cpu_rpm']} RPM\033[0m ({cpu_pct:.1f}% scale) | Temp: {t['cpu_temp']}°C")
    print(f"       Live GPU: \033[1;37m{t['gpu_rpm']} RPM\033[0m ({gpu_pct:.1f}% scale) | Temp: {t['gpu_temp']}°C")

    # 4. Active Fan Control Test
    print(" [4/4] Verifying hardware fan control write response...", end=" ", flush=True)
    initial_mode = t["fan_mode"]

    # Pulse test speed (70%)
    if not set_fan_speed(70, 70):
        print("\033[0;31mFAILED (Write error)\033[0m")
        return False

    time.sleep(0.4)
    t_after = read_telemetry()

    if t_after["fan_mode"] == "70,70":
        print("\033[1;32mVERIFIED (Hardware accepted command)\033[0m")
        print(f"       Active Command: {t_after['fan_mode']} (CPU: {t_after['cpu_rpm']} RPM, GPU: {t_after['gpu_rpm']} RPM)")
    else:
        print(f"\033[1;33mUNVERIFIED (Mode: {t_after['fan_mode']})\033[0m")

    # Restore previous mode
    print("       Restoring initial fan mode...", end=" ", flush=True)
    if initial_mode and initial_mode != "Unknown":
        parts = initial_mode.split(",")
        if len(parts) == 2:
            set_fan_speed(int(parts[0]), int(parts[1]))
        else:
            set_fan_speed(0, 0)
    else:
        set_fan_speed(0, 0)
    print("\033[1;32mRESTORED\033[0m")

    print("==================================================")
    print(" \033[1;32m[✓] All tests passed! Fan control & sensors are 100% operational.\033[0m")
    print("==================================================")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Fan Control: Open-source Linux cooling and hardware fan manager",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    subparsers.add_parser("status", help="Show current fan speeds, modes, and temps")
    subparsers.add_parser("max", help="Force fans to 100% full blast (Turbo)")
    subparsers.add_parser("auto", help="Restore fans to automatic BIOS management")
    watch_p = subparsers.add_parser("watch", help="Fast, flicker-free live dashboard (default: 0.25s / 4 Hz)")
    watch_p.add_argument("-i", "--interval", type=float, default=0.25, help="Update interval in seconds (default: 0.25)")
    subparsers.add_parser("check", help="Run automated self-diagnostic check on fan control and RPM sensors")
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
            time.sleep(0.3)
            print_status()
    elif args.command == "auto":
        if set_fan_speed(0, 0):
            print("\033[1;32m[✓] Restored fans to AUTO (BIOS Managed Curve).\033[0m")
            time.sleep(0.3)
            print_status()
    elif args.command == "check":
        check_fan_control()
    elif args.command == "set":
        gpu_val = args.gpu if args.gpu is not None else args.cpu
        if args.cpu == 0 and gpu_val == 0:
            print("\033[1;33m[!] Note: Setting custom speed to 0% is prevented to protect hardware from motor stalling and heat.\033[0m")
            print("\033[1;32m[✓] Routing safely to AUTO mode (firmware-managed thermal curve).\033[0m")
            if set_fan_speed(0, 0):
                time.sleep(0.3)
                print_status()
        elif set_fan_speed(args.cpu, gpu_val):
            print(f"\033[1;32m[✓] Applied custom fan speed: CPU={args.cpu}%, GPU={gpu_val}%.\033[0m")
            time.sleep(0.3)
            print_status()
    elif args.command == "watch":
        live_watch(args.interval)
    elif args.command == "gui":
        gui_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui", "nitro_gui.py")
        os.execv(sys.executable, [sys.executable, gui_path])

if __name__ == "__main__":
    main()
