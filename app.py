"""
Cisco SG300-28 Portable Monitor
Backend Flask app with SNMP polling
"""

from flask import Flask, jsonify, render_template, request
import threading
import time
import json
from datetime import datetime, timedelta
from pysnmp.hlapi import *

app = Flask(__name__)

# ─── Global state ───────────────────────────────────────────────────────────
device_data = {
    "host": "",
    "community": "public",
    "connected": False,
    "last_update": None,
    "sysName": "—",
    "sysDescr": "—",
    "sysUptime": "—",
    "sysUptime_secs": 0,
    "cpu": 0,
    "memory_used": 0,
    "memory_total": 0,
    "interfaces": [],
    "history": {
        "timestamps": [],
        "cpu": [],
    },
    "error": "",
}

poll_thread = None
poll_active = False

# ─── SNMP OIDs ───────────────────────────────────────────────────────────────
OID_SYSNAME       = "1.3.6.1.2.1.1.5.0"
OID_SYSDESCR      = "1.3.6.1.2.1.1.1.0"
OID_SYSUPTIME     = "1.3.6.1.2.1.1.3.0"

# Cisco SG300-specific CPU (rlCpuUtilDuringLastMinute)
OID_CPU_MIN       = "1.3.6.1.4.1.9.6.1.84.1.2.1.0"  # 1-min avg
OID_CPU_SEC       = "1.3.6.1.4.1.89.1.7.0"           # realtime (Radlan/Marvell)

# Memory
OID_MEM_TOTAL     = "1.3.6.1.4.1.9.6.1.84.1.3.1.0"
OID_MEM_FREE      = "1.3.6.1.4.1.9.6.1.84.1.3.2.0"

# IF-MIB table columns
OID_IF_NUM        = "1.3.6.1.2.1.2.1.0"
OID_IF_DESCR      = "1.3.6.1.2.1.2.2.1.2"
OID_IF_ADMINSTATUS= "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPERSTATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IF_SPEED      = "1.3.6.1.2.1.2.2.1.5"
OID_IF_IN_OCTETS  = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_IN_ERRORS  = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"
OID_IF_IN_DISCARDS= "1.3.6.1.2.1.2.2.1.13"

import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

# ─── SNMP helpers ────────────────────────────────────────────────────────────

async def _async_snmp_get(host, community, oid):
    try:
        transport = await UdpTransportTarget.create((host, 161), timeout=10, retries=3)
        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        if errorIndication:
            return None, str(errorIndication)
        if errorStatus:
            return None, errorStatus.prettyPrint()
        return varBinds[0][1], None
    except Exception as e:
        return None, str(e)

def snmp_get(host, community, oid):
    """Single SNMP GET. Returns (value, error_string)."""
    return asyncio.run(_async_snmp_get(host, community, oid))


async def _async_snmp_walk(host, community, oid):
    results = []
    try:
        transport = await UdpTransportTarget.create((host, 161), timeout=10, retries=3)
        async for errorIndication, errorStatus, errorIndex, varBinds in next_cmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if errorIndication or errorStatus:
                break
            for varBind in varBinds:
                oid_str = str(varBind[0])
                index = oid_str.split(".")[-1]
                results.append((index, varBind[1]))
    except Exception:
        pass
    return results

def snmp_walk(host, community, oid):
    """SNMP WALK. Returns list of (index, value) tuples."""
    return asyncio.run(_async_snmp_walk(host, community, oid))


def format_uptime(centiseconds):
    try:
        secs = int(centiseconds) // 100
        td = timedelta(seconds=secs)
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours:02d}:{minutes:02d}:{seconds:02d}", secs
    except Exception:
        return "—", 0


# ─── Polling loop ─────────────────────────────────────────────────────────────

def poll_device():
    global device_data, poll_active
    prev_in  = {}
    prev_out = {}
    prev_time = {}

    while poll_active:
        host      = device_data["host"]
        community = device_data["community"]

        if not host:
            time.sleep(2)
            continue

        try:
            # System info
            sysname,  err = snmp_get(host, community, OID_SYSNAME)
            if sysname is None and err:
                raise Exception(f"Error SNMP con IP {host}: {err}")

            sysdescr, _ = snmp_get(host, community, OID_SYSDESCR)
            uptime,   _ = snmp_get(host, community, OID_SYSUPTIME)

            up_str, up_secs = format_uptime(uptime) if uptime else ("—", 0)

            # CPU  — try both OIDs
            cpu_val, _ = snmp_get(host, community, OID_CPU_SEC)
            if cpu_val is None:
                cpu_val, _ = snmp_get(host, community, OID_CPU_MIN)
            cpu = int(cpu_val) if cpu_val is not None else 0

            # Memory
            mem_total_raw, _ = snmp_get(host, community, OID_MEM_TOTAL)
            mem_free_raw,  _ = snmp_get(host, community, OID_MEM_FREE)
            mem_total = int(mem_total_raw) if mem_total_raw is not None else 0
            mem_free  = int(mem_free_raw)  if mem_free_raw  is not None else 0
            mem_used  = mem_total - mem_free

            # Interfaces
            descrs       = {i: str(v) for i, v in snmp_walk(host, community, OID_IF_DESCR)}
            admin_states = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_ADMINSTATUS)}
            oper_states  = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_OPERSTATUS)}
            speeds       = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_SPEED)}
            in_octets    = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_IN_OCTETS)}
            out_octets   = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_OUT_OCTETS)}
            in_errors    = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_IN_ERRORS)}
            out_errors   = {i: int(v)  for i, v in snmp_walk(host, community, OID_IF_OUT_ERRORS)}

            now = time.time()
            interfaces = []
            for idx in sorted(descrs.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                if int(idx) > 28 and not descrs.get(idx, "").startswith("gi"):
                    # skip VLAN and other virtual interfaces > port 28
                    pass

                in_o  = in_octets.get(idx, 0)
                out_o = out_octets.get(idx, 0)

                # calc Mbps
                in_mbps  = 0.0
                out_mbps = 0.0
                if idx in prev_in and idx in prev_time:
                    dt = now - prev_time[idx]
                    if dt > 0:
                        in_mbps  = (in_o  - prev_in.get(idx, 0))  * 8 / 1_000_000 / dt
                        out_mbps = (out_o - prev_out.get(idx, 0)) * 8 / 1_000_000 / dt
                        in_mbps  = max(0, in_mbps)
                        out_mbps = max(0, out_mbps)

                prev_in[idx]   = in_o
                prev_out[idx]  = out_o
                prev_time[idx] = now

                speed_raw = speeds.get(idx, 0)
                speed_mbps = speed_raw // 1_000_000 if speed_raw else 0

                oper = oper_states.get(idx, 2)
                admin = admin_states.get(idx, 2)

                interfaces.append({
                    "index":      int(idx),
                    "name":       descrs.get(idx, f"Port {idx}"),
                    "admin":      "up" if admin == 1 else "down",
                    "status":     "up" if oper == 1 else "down",
                    "speed_mbps": speed_mbps,
                    "in_mbps":    round(in_mbps, 3),
                    "out_mbps":   round(out_mbps, 3),
                    "in_errors":  in_errors.get(idx, 0),
                    "out_errors": out_errors.get(idx, 0),
                    "in_octets":  in_o,
                    "out_octets": out_o,
                })

            # Update history (keep last 60 points)
            ts = datetime.now().strftime("%H:%M:%S")
            device_data["history"]["timestamps"].append(ts)
            device_data["history"]["cpu"].append(cpu)
            if len(device_data["history"]["timestamps"]) > 60:
                device_data["history"]["timestamps"].pop(0)
                device_data["history"]["cpu"].pop(0)

            device_data.update({
                "connected":      True,
                "error":          "",
                "last_update":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sysName":        str(sysname)  if sysname  else "—",
                "sysDescr":       str(sysdescr) if sysdescr else "—",
                "sysUptime":      up_str,
                "sysUptime_secs": up_secs,
                "cpu":            cpu,
                "memory_used":    mem_used,
                "memory_total":   mem_total,
                "interfaces":     interfaces,
            })

        except Exception as e:
            device_data["connected"] = False
            device_data["error"] = str(e)

        time.sleep(10)  # poll every 10 seconds


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/connect", methods=["POST"])
def connect():
    global poll_thread, poll_active

    data = request.get_json()
    host      = data.get("host", "").strip()
    community = data.get("community", "public").strip()

    if not host:
        return jsonify({"ok": False, "error": "Host requerido"})

    device_data["host"]      = host
    device_data["community"] = community
    device_data["connected"] = False
    device_data["error"]     = ""
    device_data["interfaces"] = []
    device_data["history"]   = {"timestamps": [], "cpu": []}

    # Start/restart polling thread
    poll_active = False
    if poll_thread and poll_thread.is_alive():
        poll_thread.join(timeout=3)

    poll_active = True
    poll_thread = threading.Thread(target=poll_device, daemon=True)
    poll_thread.start()

    return jsonify({"ok": True})


@app.route("/api/status")
def status():
    return jsonify(device_data)


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    global poll_active
    poll_active = False
    device_data["connected"] = False
    device_data["host"] = ""
    device_data["interfaces"] = []
    return jsonify({"ok": True})


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Cisco SG300-28 Monitor  |  http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
