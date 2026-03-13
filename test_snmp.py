import sys
import asyncio
from pysnmp.hlapi.v3arch.asyncio import *

async def run_get(host, community, oid):
    print(f"Testing SNMP GET for {host} with community '{community}' (OID {oid})")
    try:
        transport = await UdpTransportTarget.create((host, 161), timeout=5, retries=2)
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
    return asyncio.run(run_get(host, community, oid))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_snmp.py <IP> <COMMUNITY>")
        sys.exit(1)
        
    ip = sys.argv[1]
    comm = sys.argv[2]
    
    val, err = snmp_get(ip, comm, "1.3.6.1.2.1.1.1.0")
    if err:
        print(f"ERROR: {err}")
    else:
        print(f"SUCCESS! SysDescr: {val}")
