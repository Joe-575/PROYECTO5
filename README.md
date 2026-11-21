# Sistema Bayesiano de Interpretación Probabilística de Alertas Informáticas

Sistema de diagnóstico probabilístico para entornos de ciberseguridad (SOC) basado en una **Red Bayesiana binaria**. Permite inferir las causas más probables detrás de alertas de red y registros de seguridad utilizando un **motor propio de inferencia exacta por enumeración** (sin bibliotecas externas), validado de forma cruzada con **`pgmpy`** (Eliminación de Variables), e incluye tanto una **interfaz web interactiva** como una **interfaz de consola**.

---

## ¿De qué trata este repositorio?

En un centro de operaciones de seguridad (SOC), una misma alerta puede deberse a una intrusión real, a un error de configuración o a tareas legítimas de mantenimiento. Este proyecto modela dichas relaciones causa-efecto mediante una Red Bayesiana de 6 variables binarias:

### Estructura de la Red Bayesiana (DAG)

- **Causas raíz (variables ocultas):**
  - `I`: Intrusión externa (ataque activo o acceso no autorizado)
  - `C`: Error de configuración (reglas de firewall, DNS o permisos)
  - `M`: Mantenimiento o actividad legítima intensa (respaldos, escaneos autorizados)
- **Señales observables (evidencia):**
  - `T`: Tráfico anómalo en red — depende de `I`, `M`
  - `A`: Alerta del sistema IDS/SIEM — depende de `I`, `C`
  - `L`: Fallos de autenticación o bloqueo de cuentas en logs — depende de `I`, `C`

### Capacidades principales

1. **Inferencia exacta en tiempo real**: Calcula `P(X | e)` mediante `ENUMERATION-ASK` y `ENUMERATE-ALL` implementados desde cero en Python puro.
2. **Evaluación de 4 escenarios predefinidos**:
   - *Escenario 1*: Una sola alerta observada (`A=True`).
   - *Escenario 2*: Varias señales simultáneas (`A=True, T=True, L=True`).
   - *Escenario 3*: Alerta con evidencia de causa alternativa (`A=True, C=True` — efecto *explaining away*).
   - *Escenario 4*: Ausencia de señal esperada (`A=False, T=True, L=True`).
3. **Verificación cruzada con `pgmpy`**: Compara el algoritmo propio contra el algoritmo de Eliminación de Variables de `pgmpy` reportando la diferencia absoluta.
4. **Comparación de probabilidades previas (`P(I)`)**: Analiza cómo cambia `P(I=True | e)` al pasar de operación normal (`2%`) a alerta temprana por ciberinteligencia (`20%`), junto con curva de sensibilidad.
5. **Edición de tablas CPT en vivo**: Permite ajustar probabilidades en memoria durante pruebas o defensas sin sobreescribir `red_alertas.json`.

---

## Estructura del proyecto

```text
PROYECTO5_ALERTAS/
├── inferencia_bayesiana.py   # Motor propio de inferencia exacta por enumeración
├── verificacion_pgmpy.py     # Módulo de verificación cruzada usando pgmpy
├── main.py                   # Interfaz de consola (menú interactivo)
├── red_alertas.json          # Definición de variables, topología y tablas CPT
├── escenarios.json           # 4 escenarios de prueba y parámetros de comparación
├── app_web.py                # Servidor web ligero (solo biblioteca estándar de Python)
├── web/
│   ├── index.html            # Interfaz gráfica web (HTML5)
│   ├── styles.css            # Estilos profesionales con modo oscuro/claro (CSS3)
│   └── app.js                # Grafo DAG interactivo, gráficos SVG y lógica cliente
├── requirements.txt          # Dependencia opcional/recomendada (pgmpy)
└── README.md
```

---

## Requisitos previos

- **Python 3.9 o superior** ([descargar aquí](https://www.python.org/downloads/)).
- **Para la interfaz web (`app_web.py`)**: **No requiere instalar ninguna librería externa** para funcionar con el motor propio. Si además instalas `pgmpy`, la verificación cruzada se activará automáticamente.
- **Para la interfaz de consola (`main.py`) o verificación cruzada**: Requiere instalar `pgmpy`.

---

## Instalación

1. Clona o descarga el repositorio:

```bash
git clone <https://github.com/Joe-575/PROYECTO5>
cd PROYECTO5_ALERTAS
```

2. *(Opcional, recomendado)* Crea y activa un entorno virtual:

- **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  ```
- **Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

3. *(Requerido para `main.py` y para activar verificación `pgmpy` en la web)* Instala las dependencias:

```bash
pip install -r requirements.txt
```

---

## Cómo ejecutarlo

### Opción 1: Interfaz Gráfica Web (Recomendada)

```bash
python app_web.py
```

- Abrirá automáticamente el navegador en `http://127.0.0.1:8080`.
- Puedes cambiar el puerto si el `8080` está ocupado:
  - **Windows (PowerShell):** `$env:PORT="8081"; python app_web.py`
  - **Linux / macOS:** `PORT=8081 python3 app_web.py`
- Para detener el servidor, presiona `Ctrl + C` en la terminal.

### Opción 2: Interfaz de Consola (CLI)

```bash
python main.py
```

Muestra un menú interactivo en terminal para ejecutar los 4 escenarios con `pgmpy`, comparar probabilidades previas, hacer consultas personalizadas y editar CPTs en vivo.
