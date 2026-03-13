# Cisco SG300-28 Portable Monitor

Una herramienta ligera, portátil y moderna (Dark Theme + Glassmorphism) para monitorear en tiempo real un switch Cisco SG300-28 vía protocolo SNMP.

## Características

*   **100% Portátil:** No requiere instalación de base de datos ni servidor web pesado.
*   **Monitoreo en Tiempo Real:** Realiza polling SNMP cada 10 segundos.
*   **Métricas Clave:**
    *   Uptime y estado general
    *   Uso de CPU (Gráfico en tiempo real)
    *   Uso de Memoria (Barra de progreso)
    *   Estado visual de los 28 puertos
    *   Tráfico entrante (RX) y saliente (TX) en Mbps
    *   Contador de errores por interfaz
*   **Interfaz Moderna:** Diseño oscuro (Dark Mode), responsivo y profesional.

## Requisitos

*   Python 3.8 o superior (`python.org`)
*   Acceso por red al switch Cisco SG300-28
*   SNMP habilitado en el switch (v1/v2c)

## Instalación y Uso (Windows)

1.  Abre la carpeta del proyecto.
2.  Haz doble clic en el archivo `start.bat`.
    *(La primera vez, instalará automáticamente las dependencias necesarias `flask` y `pysnmp`)*.
3.  El servidor se iniciará. Abre tu navegador e ingresa a: `http://localhost:5000`
4.  Ingresa la IP del switch y tu comunidad SNMP (por defecto suele ser `public`).
5.  ¡Listo! Verás el estado de tu equipo en tiempo real.

## Uso (Linux/Mac)

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Ejecutar la app
python app.py
```
Luego visita `http://localhost:5000` en tu navegador.
