import socket
import pyvjoy
import time
import os
import sys
import ctypes

# --- Firewall rule setup ---
def add_firewall_rule(app_name, exe_path):
    rule_cmd = f'netsh advfirewall firewall add rule name="{app_name}" dir=in action=allow program="{exe_path}" enable=yes'
    os.system(rule_cmd)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    # Relaunch with admin rights
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()

# Add firewall rule for this executable
add_firewall_rule("FlightControls", sys.executable)

# --- UDP server setup ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()

UDP_IP = get_local_ip()
UDP_PORT = 9876

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

j = pyvjoy.VJoyDevice(1)

ref_roll = ref_pitch = ref_yaw = None
last_axes = (0, 0, 0)
keep_reference = False
manual_yaw_override = None

def normalize(value, center, range_span=90):
    min_input = center - range_span
    max_input = center + range_span
    scaled = int((value - min_input) / (max_input - min_input) * 0x8000)
    return max(0, min(scaled, 0x8000))

print(f"[INFO] UDP server listening on {UDP_IP}:{UDP_PORT}")

mapping = {
    "gear": 1, "b2": 2, "b0": 9, "b1": 10, "b3": 11,
    "b6": 8, "b7": 7, "b4": 12, "b5": 13, "b8": 14,
    "brakes": 3, "spoiler": 4, "b9": 15, "b10": 16,
    "flapsup": 5, "flapsdown": 6, "b11": 17, "b12": 18,
    "b13": 19, "b14": 20, "b15": 21, "b16": 22, "b17": 23,
    "b18":24, "b19":25, "b20":26, "b21":27, "b22":28,
}

while True:
    data, _ = sock.recvfrom(1024)
    msg = data.decode().strip()
    button_states = {i: 0 for i in range(1, 33)}

    if msg.startswith("btn:"):
        btn_full = msg.split(":")[1]

        if btn_full.endswith("_down") or btn_full.endswith("_up"):
            state = 1 if btn_full.endswith("_down") else 0
            btn = btn_full.rsplit("_", 1)[0]

            if btn in mapping:
                button_id = mapping[btn]
                button_states[button_id] = state
                j.data.lButtons = sum(1 << (i - 1) for i, v in button_states.items() if v)
                action = "pressed" if state else "released"
                print(f"[INPUT] Button '{btn}' {action}")

    elif msg.startswith("throttle:"):
        val = int(msg.split(":")[1])
        j.data.wAxisXRot = int(val / 100 * 0x8000)
        j.update()

    elif msg == "lr":
        ref_roll = ref_pitch = ref_yaw = None
        print("[INFO] Reference reset requested")

    elif msg == "kr":
        keep_reference = not keep_reference
        print(f"[INFO] Keep Reference toggled to: {keep_reference}")

    elif msg.startswith("manual_yaw:"):
        val = int(msg.split(":")[1])
        j.data.wAxisYRot = int(val / 100 * 0x8000)
        j.update()

    elif "," in msg:
        try:
            roll, pitch, yaw = map(float, msg.split(","))
            if ref_roll is None or ref_pitch is None:
                ref_roll, ref_pitch = roll, pitch
                manual_yaw_override = 0
                print(f"[INFO] Reference locked: R={ref_roll}, P={ref_pitch}")

            current_yaw = manual_yaw_override if manual_yaw_override is not None else yaw

            if not keep_reference:
                last_axes = (roll, pitch)
            else:
                last_axes = (ref_roll, ref_pitch)

            j.data.wAxisX = normalize(last_axes[0], ref_roll)
            j.data.wAxisY = normalize(last_axes[1], ref_pitch)
            j.update()

        except ValueError:
            pass
