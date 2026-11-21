"""
Programa principal: Sistema de interpretacion probabilistica de alertas informaticas.
Permite ejecutar los escenarios predefinidos, verificar con pgmpy y realizar
consultas o cambios de parametros en vivo.
"""

import json
from typing import Dict
from inferencia_bayesiana import RedBayesiana
from verificacion_pgmpy import construir_modelo_pgmpy, consultar_pgmpy


def ejecutar_escenarios(red: RedBayesiana, config_escenarios: dict):
    motor_pgmpy = construir_modelo_pgmpy(red)
    causas = config_escenarios["causas_objetivo"]

    print("\n" + "=" * 78)
    print("EVALUACION DE LOS 4 ESCENARIOS Y VERIFICACION CON PGMPY")
    print("=" * 78)

    for esc in config_escenarios["escenarios"]:
        print(f"\n>>> {esc['nombre']}")
        print(f"    Contexto : {esc['descripcion']}")
        print(f"    Evidencia: {esc['evidencia']}")
        print("-" * 78)
        print(
            f"{'Causa':<8} | {'P(True) Propio':>15} | {'P(True) pgmpy':>15} | {'Diff Abs':>12}"
        )
        print("-" * 78)

        for causa in causas:
            res_propio = red.enumeration_ask(causa, esc["evidencia"])
            res_lib = consultar_pgmpy(motor_pgmpy, causa, esc["evidencia"])
            diff = abs(res_propio[True] - res_lib[True])
            print(
                f"{causa:<8} | {res_propio[True]:>14.6f} | {res_lib[True]:>14.6f} | {diff:>12.2e}"
            )


def ejecutar_comparacion_previas(red: RedBayesiana, config_escenarios: dict):
    comp = config_escenarios["comparacion_previa"]
    esc = next(
        e for e in config_escenarios["escenarios"] if e["id"] == comp["escenario_id"]
    )

    red_base = red.clonar()
    red_base.actualizar_probabilidad_previa("I", comp["previa_base"])

    red_alta = red.clonar()
    red_alta.actualizar_probabilidad_previa("I", comp["previa_alta"])

    post_base = red_base.enumeration_ask("I", esc["evidencia"])
    post_alta = red_alta.enumeration_ask("I", esc["evidencia"])

    print("\n" + "=" * 78)
    print("COMPARACION DE PROBABILIDADES PREVIAS DE INTRUSION (MISMA EVIDENCIA)")
    print("=" * 78)
    print(f"Escenario evaluado : {esc['nombre']} -> Evidencia: {esc['evidencia']}")
    print(f"Justificacion      : {comp['justificacion']}\n")
    print(
        f"{'Condicion':<28} | {'Previa P(I=T)':>14} | {'Posterior P(I=T|e)':>18} | {'Posterior P(I=F|e)':>18}"
    )
    print("-" * 78)
    print(
        f"{'Operacion normal':<28} | {comp['previa_base']:>13.2%} | {post_base[True]:>17.6f} | {post_base[False]:>17.6f}"
    )
    print(
        f"{'Alerta ciberinteligencia':<28} | {comp['previa_alta']:>13.2%} | {post_alta[True]:>17.6f} | {post_alta[False]:>17.6f}"
    )


def consulta_interactiva(red: RedBayesiana):
    print("\n--- CONSULTA PERSONALIZADA (MODO DEFENSA EN VIVO) ---")
    print("Variables disponibles:", ", ".join(red.orden_topologico))
    var_consulta = input("Variable a consultar (ej. I, C, M): ").strip().upper()
    if var_consulta not in red.nodos:
        print("Variable no valida.")
        return

    print("Ingrese evidencia en formato VAR=true/false separada por comas (ej. A=true,T=false)")
    entrada_ev = input("Evidencia (deje vacio si no hay evidencia): ").strip()
    evidencia: Dict[str, bool] = {}

    if entrada_ev:
        try:
            for par in entrada_ev.split(","):
                k, v = par.strip().split("=")
                k = k.strip().upper()
                v_str = v.strip().lower()
                if k not in red.nodos or v_str not in ("true", "false"):
                    raise ValueError
                evidencia[k] = v_str == "true"
        except ValueError:
            print("Formato invalido. Use VAR=true o VAR=false.")
            return

    res_propio = red.enumeration_ask(var_consulta, evidencia)
    motor_pgmpy = construir_modelo_pgmpy(red)
    res_lib = consultar_pgmpy(motor_pgmpy, var_consulta, evidencia)

    print(f"\nResultados para P({var_consulta} | {evidencia}):")
    print(f"  Algoritmo propio -> True: {res_propio[True]:.6f} ({res_propio[True]:.2%}) | False: {res_propio[False]:.6f} ({res_propio[False]:.2%})")
    print(f"  Verif. pgmpy     -> True: {res_lib[True]:.6f} ({res_lib[True]:.2%}) | False: {res_lib[False]:.6f} ({res_lib[False]:.2%})")


def modificar_parametro_en_vivo(red: RedBayesiana):
    print("\n--- MODIFICAR PROBABILIDAD EN VIVO ---")
    var = input("Variable a modificar (I, C, M, T, A, L): ").strip().upper()
    if var not in red.nodos:
        print("Variable no valida.")
        return

    nodo = red.nodos[var]
    print(f"Padres de {var}: {nodo['padres']}")
    print("Entradas actuales de CPT:", nodo["cpt"])
    clave = input("Clave exacta a modificar (deje vacio si es nodo raiz): ").strip().lower()
    if clave not in nodo["cpt"]:
        print("Clave no encontrada en la CPT.")
        return

    try:
        nuevo_val = float(input("Nueva probabilidad para True (entre 0 y 1): ").strip())
        if not (0.0 <= nuevo_val <= 1.0):
            raise ValueError
        nodo["cpt"][clave] = nuevo_val
        print(f"Parametro actualizado: P({var}=True | {clave or 'sin padres'}) = {nuevo_val:.4f}")
    except ValueError:
        print("Valor numerico invalido.")


def menu():
    red = RedBayesiana(ruta_json="red_alertas.json")
    with open("escenarios.json", "r", encoding="utf-8") as f:
        config_escenarios = json.load(f)

    while True:
        print("\n" + "=" * 55)
        print(" SISTEMA BAYESIANO DE INTERPRETACION DE ALERTAS ")
        print("=" * 55)
        print("1. Ejecutar los 4 escenarios y verificar con pgmpy")
        print("2. Comparar probabilidades previas de intrusion")
        print("3. Realizar consulta personalizada (evidencia libre)")
        print("4. Modificar un parametro de CPT en vivo")
        print("5. Salir")

        opcion = input("Seleccione una opcion: ").strip()
        if opcion == "1":
            ejecutar_escenarios(red, config_escenarios)
        elif opcion == "2":
            ejecutar_comparacion_previas(red, config_escenarios)
        elif opcion == "3":
            consulta_interactiva(red)
        elif opcion == "4":
            modificar_parametro_en_vivo(red)
        elif opcion == "5":
            break
        else:
            print("Opcion no valida.")


if __name__ == "__main__":
    menu()