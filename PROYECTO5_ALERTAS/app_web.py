"""
Servidor web ligero (biblioteca estandar de Python) para la interfaz grafica
del Sistema Bayesiano de Interpretacion de Alertas Informaticas.

No modifica ningun archivo del codigo base; importa directamente RedBayesiana
y, si esta disponible en el entorno, el modulo de verificacion con pgmpy.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from inferencia_bayesiana import RedBayesiana

try:
    from verificacion_pgmpy import construir_modelo_pgmpy, consultar_pgmpy

    PGMPY_DISPONIBLE = True
    PGMPY_ERROR = None
except Exception as exc:  # pragma: no cover - entorno sin pgmpy
    PGMPY_DISPONIBLE = False
    PGMPY_ERROR = str(exc)

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
RUTA_RED = BASE_DIR / "red_alertas.json"
RUTA_ESCENARIOS = BASE_DIR / "escenarios.json"


class EstadoSistema:
    """Mantiene la instancia activa de la red y cachea el motor pgmpy."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.red: RedBayesiana = RedBayesiana(ruta_json=str(RUTA_RED))
        self.datos_originales: dict = json.loads(RUTA_RED.read_text(encoding="utf-8"))
        self.config_escenarios: dict = json.loads(
            RUTA_ESCENARIOS.read_text(encoding="utf-8")
        )
        self._motor_pgmpy: Any = None
        self.modificado: bool = False

    def obtener_motor_pgmpy(self) -> Any:
        if not PGMPY_DISPONIBLE:
            return None
        with self._lock:
            if self._motor_pgmpy is None:
                self._motor_pgmpy = construir_modelo_pgmpy(self.red)
            return self._motor_pgmpy

    def invalidar_cache(self) -> None:
        with self._lock:
            self._motor_pgmpy = None

    def reiniciar(self) -> None:
        with self._lock:
            self.red = RedBayesiana(ruta_json=str(RUTA_RED))
            self._motor_pgmpy = None
            self.modificado = False

    def actualizar_cpt(self, variable: str, clave: str, valor: float) -> dict:
        with self._lock:
            if variable not in self.red.nodos:
                raise KeyError(f"Variable desconocida: {variable}")
            cpt = self.red.nodos[variable]["cpt"]
            if clave not in cpt:
                raise KeyError(f"Clave CPT desconocida '{clave}' para {variable}")
            if not (0.0 <= valor <= 1.0):
                raise ValueError("La probabilidad debe estar entre 0.0 y 1.0.")

            cpt[clave] = round(float(valor), 6)
            self._motor_pgmpy = None
            self.modificado = (
                self.red.nodos != self.datos_originales["nodos"]
            )
            return {
                "variable": variable,
                "clave": clave,
                "valor": cpt[clave],
                "modificado": self.modificado,
            }

    def inferir_todo(
        self,
        evidencia: Dict[str, bool],
        variable_consulta: Optional[str] = None,
        verificar_pgmpy: bool = True,
    ) -> dict:
        with self._lock:
            t0 = time.perf_counter()
            posteriores: Dict[str, Dict[str, float]] = {}
            for var in self.red.orden_topologico:
                res = self.red.enumeration_ask(var, evidencia)
                posteriores[var] = {
                    "true": float(res[True]),
                    "false": float(res[False]),
                }
            tiempo_propio_ms = (time.perf_counter() - t0) * 1000.0

            verificacion = None
            if verificar_pgmpy and PGMPY_DISPONIBLE:
                t1 = time.perf_counter()
                motor = self.obtener_motor_pgmpy()
                objetivos = (
                    [variable_consulta]
                    if variable_consulta and variable_consulta in self.red.nodos
                    else self.config_escenarios["causas_objetivo"]
                )
                verif_vars = {}
                for var in objetivos:
                    res_lib = consultar_pgmpy(motor, var, evidencia)
                    p_propio = posteriores[var]["true"]
                    p_lib = float(res_lib[True])
                    verif_vars[var] = {
                        "true": p_lib,
                        "false": float(res_lib[False]),
                        "diff_abs": abs(p_propio - p_lib),
                    }
                tiempo_pgmpy_ms = (time.perf_counter() - t1) * 1000.0
                verificacion = {
                    "disponible": True,
                    "resultados": verif_vars,
                    "tiempo_ms": round(tiempo_pgmpy_ms, 3),
                }
            else:
                verificacion = {
                    "disponible": False,
                    "motivo": PGMPY_ERROR or "Desactivado",
                }

            return {
                "evidencia": evidencia,
                "posteriores": posteriores,
                "tiempo_propio_ms": round(tiempo_propio_ms, 3),
                "verificacion_pgmpy": verificacion,
            }

    def evaluar_escenarios(self) -> dict:
        with self._lock:
            causas = self.config_escenarios["causas_objetivo"]
            motor = self.obtener_motor_pgmpy() if PGMPY_DISPONIBLE else None
            resultados = []

            t0 = time.perf_counter()
            for esc in self.config_escenarios["escenarios"]:
                evidencia = {k: bool(v) for k, v in esc["evidencia"].items()}
                filas = []
                for causa in causas:
                    res_propio = self.red.enumeration_ask(causa, evidencia)
                    p_propio = float(res_propio[True])
                    p_lib = None
                    diff = None
                    if motor is not None:
                        res_lib = consultar_pgmpy(motor, causa, evidencia)
                        p_lib = float(res_lib[True])
                        diff = abs(p_propio - p_lib)
                    filas.append(
                        {
                            "causa": causa,
                            "nombre": self.red.variables[causa],
                            "p_propio": p_propio,
                            "p_pgmpy": p_lib,
                            "diff_abs": diff,
                        }
                    )
                resultados.append(
                    {
                        "id": esc["id"],
                        "nombre": esc["nombre"],
                        "descripcion": esc["descripcion"],
                        "evidencia": evidencia,
                        "resultados": filas,
                    }
                )
            total_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "causas_objetivo": causas,
                "pgmpy_disponible": PGMPY_DISPONIBLE,
                "tiempo_ms": round(total_ms, 3),
                "escenarios": resultados,
            }

    def comparar_previas(
        self,
        escenario_id: Optional[int] = None,
        previa_base: Optional[float] = None,
        previa_alta: Optional[float] = None,
    ) -> dict:
        with self._lock:
            comp = self.config_escenarios["comparacion_previa"]
            esc_id = escenario_id if escenario_id is not None else comp["escenario_id"]
            p_base = float(previa_base if previa_base is not None else comp["previa_base"])
            p_alta = float(previa_alta if previa_alta is not None else comp["previa_alta"])

            if not (0.0 <= p_base <= 1.0 and 0.0 <= p_alta <= 1.0):
                raise ValueError("Las probabilidades previas deben estar en [0, 1].")

            esc = next(
                (e for e in self.config_escenarios["escenarios"] if e["id"] == esc_id),
                self.config_escenarios["escenarios"][0],
            )
            evidencia = {k: bool(v) for k, v in esc["evidencia"].items()}

            red_base = self.red.clonar()
            red_base.actualizar_probabilidad_previa("I", p_base)
            post_base = red_base.enumeration_ask("I", evidencia)

            red_alta = self.red.clonar()
            red_alta.actualizar_probabilidad_previa("I", p_alta)
            post_alta = red_alta.enumeration_ask("I", evidencia)

            # Curva de sensibilidad de P(I=True | e) frente a P(I=True)
            puntos_curva = []
            for pct in (1, 2, 5, 10, 15, 20, 25, 30, 40, 50):
                prior = pct / 100.0
                red_tmp = self.red.clonar()
                red_tmp.actualizar_probabilidad_previa("I", prior)
                post_tmp = red_tmp.enumeration_ask("I", evidencia)
                puntos_curva.append(
                    {"previa": prior, "posterior": float(post_tmp[True])}
                )

            return {
                "escenario": esc,
                "justificacion": comp["justificacion"],
                "base": {
                    "etiqueta": "Operacion normal",
                    "previa": p_base,
                    "posterior_true": float(post_base[True]),
                    "posterior_false": float(post_base[False]),
                },
                "alta": {
                    "etiqueta": "Alerta ciberinteligencia",
                    "previa": p_alta,
                    "posterior_true": float(post_alta[True]),
                    "posterior_false": float(post_alta[False]),
                },
                "curva_sensibilidad": puntos_curva,
            }


ESTADO = EstadoSistema()


class ManejadorWeb(BaseHTTPRequestHandler):
    """Manejador HTTP para archivos estaticos y API REST JSON."""

    server_version = "BayesianAlertsUI/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        # Log compacto en consola
        print(f"[HTTP] {self.address_string()} - {format % args}")

    def _enviar_json(self, datos: dict, status: int = HTTPStatus.OK) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _leer_json(self) -> dict:
        longitud = int(self.headers.get("Content-Length", "0"))
        if longitud <= 0:
            return {}
        raw = self.rfile.read(longitud)
        return json.loads(raw.decode("utf-8"))

    def _servir_archivo(self, ruta_relativa: str) -> None:
        if ruta_relativa in ("", "/"):
            ruta_relativa = "index.html"
        else:
            ruta_relativa = ruta_relativa.lstrip("/")

        archivo = (WEB_DIR / ruta_relativa).resolve()
        if not str(archivo).startswith(str(WEB_DIR.resolve())) or not archivo.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Recurso no encontrado")
            return

        tipo_mime, _ = mimetypes.guess_type(str(archivo))
        if not tipo_mime:
            tipo_mime = "application/octet-stream"
        if tipo_mime.startswith("text/") or tipo_mime in (
            "application/javascript",
            "application/json",
            "image/svg+xml",
        ):
            tipo_mime += "; charset=utf-8"

        contenido = archivo.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", tipo_mime)
        self.send_header("Content-Length", str(len(contenido)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(contenido)

    def do_GET(self) -> None:
        ruta = urlparse(self.path).path
        try:
            if ruta == "/api/estado":
                self._enviar_json(
                    {
                        "descripcion": ESTADO.red.datos.get("descripcion", ""),
                        "variables": ESTADO.red.variables,
                        "orden_topologico": ESTADO.red.orden_topologico,
                        "nodos": ESTADO.red.nodos,
                        "escenarios": ESTADO.config_escenarios,
                        "pgmpy_disponible": PGMPY_DISPONIBLE,
                        "pgmpy_error": PGMPY_ERROR,
                        "modificado": ESTADO.modificado,
                    }
                )
            elif ruta == "/api/escenarios":
                self._enviar_json(ESTADO.evaluar_escenarios())
            else:
                self._servir_archivo(ruta)
        except Exception as exc:
            self._enviar_json(
                {"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR
            )

    def do_POST(self) -> None:
        ruta = urlparse(self.path).path
        try:
            payload = self._leer_json()
            if ruta == "/api/inferencia":
                evidencia_raw = payload.get("evidencia", {})
                evidencia: Dict[str, bool] = {}
                for k, v in evidencia_raw.items():
                    if k not in ESTADO.red.nodos:
                        raise ValueError(f"Variable de evidencia invalida: {k}")
                    evidencia[k] = bool(v)
                var_consulta = payload.get("variable_consulta")
                verificar = bool(payload.get("verificar_pgmpy", True))
                self._enviar_json(
                    ESTADO.inferir_todo(
                        evidencia=evidencia,
                        variable_consulta=var_consulta,
                        verificar_pgmpy=verificar,
                    )
                )
            elif ruta == "/api/comparacion_previas":
                self._enviar_json(
                    ESTADO.comparar_previas(
                        escenario_id=payload.get("escenario_id"),
                        previa_base=payload.get("previa_base"),
                        previa_alta=payload.get("previa_alta"),
                    )
                )
            elif ruta == "/api/cpt":
                res = ESTADO.actualizar_cpt(
                    variable=str(payload["variable"]).upper(),
                    clave=str(payload.get("clave", "")).lower(),
                    valor=float(payload["valor"]),
                )
                self._enviar_json(res)
            elif ruta == "/api/reset":
                ESTADO.reiniciar()
                self._enviar_json(
                    {
                        "ok": True,
                        "nodos": ESTADO.red.nodos,
                        "modificado": ESTADO.modificado,
                    }
                )
            else:
                self._enviar_json(
                    {"error": "Endpoint no encontrado"}, status=HTTPStatus.NOT_FOUND
                )
        except (KeyError, ValueError, TypeError) as exc:
            self._enviar_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._enviar_json(
                {"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR
            )


def iniciar_servidor(
    host: str = "127.0.0.1", port: int = 8080, abrir_navegador: bool = True
) -> None:
    servidor = ThreadingHTTPServer((host, port), ManejadorWeb)
    url = f"http://{host}:{port}"
    print("=" * 64)
    print(" SISTEMA BAYESIANO DE INTERPRETACION DE ALERTAS - INTERFAZ WEB")
    print("=" * 64)
    print(f" URL local       : {url}")
    print(f" Motor propio    : Activo (inferencia_bayesiana.py)")
    print(f" Verif. pgmpy    : {'Disponible' if PGMPY_DISPONIBLE else 'No instalado en este entorno'}")
    print(" Presione Ctrl+C para detener el servidor.")
    print("=" * 64)

    if abrir_navegador:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido correctamente.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", "8080"))
    no_browser = os.environ.get("NO_BROWSER", "0") == "1"
    iniciar_servidor(port=puerto, abrir_navegador=not no_browser)
