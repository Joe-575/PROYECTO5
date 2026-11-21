"""
Modulo de verificacion cruzada mediante la biblioteca pgmpy (Eliminacion de Variables).
"""

from typing import Dict
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

# Compatibilidad: las versiones nuevas de pgmpy renombraron la clase.
try:
    from pgmpy.models import DiscreteBayesianNetwork as BayesianNetwork
except ImportError:
    from pgmpy.models import BayesianNetwork

from inferencia_bayesiana import RedBayesiana


def construir_modelo_pgmpy(red: RedBayesiana) -> VariableElimination:
    """
    Traduce dinamicamente el objeto RedBayesiana al formato de pgmpy.
    """
    # Una arista (padre, hijo) por cada dependencia declarada en el JSON.
    aristas = []
    for var, info in red.nodos.items():
        for padre in info["padres"]:
            aristas.append((padre, var))

    modelo = BayesianNetwork(aristas)
    cpds = []

    for var, info in red.nodos.items():
        padres = info["padres"]
        cpt = info["cpt"]

        if not padres:
            # Nodo raiz: una sola columna [P(False), P(True)].
            p_true = float(cpt[""])
            cpd = TabularCPD(
                variable=var,
                variable_card=2,
                values=[[1.0 - p_true], [p_true]],
                state_names={var: [False, True]},
            )
        else:
            # pgmpy exige una columna por combinacion de padres, en orden
            # lexicografico: (F,F), (F,T), (T,F), (T,T).
            num_combinaciones = 2 ** len(padres)
            probs_false = []
            probs_true = []

            for i in range(num_combinaciones):
                # Se convierte i a bits para armar la clave del JSON
                # (i=2 -> [1,0] -> "true,false").
                bits = [(i >> (len(padres) - 1 - k)) & 1 for k in range(len(padres))]
                clave = ",".join("true" if b == 1 else "false" for b in bits)
                p_t = float(cpt[clave])
                probs_true.append(p_t)
                probs_false.append(1.0 - p_t)

            # La fila 0 es False y la fila 1 es True (segun state_names).
            cpd = TabularCPD(
                variable=var,
                variable_card=2,
                values=[probs_false, probs_true],
                evidence=padres,
                evidence_card=[2] * len(padres),
                state_names={n: [False, True] for n in [var] + padres},
            )
        cpds.append(cpd)

    modelo.add_cpds(*cpds)
    # Comprueba que las tablas sean consistentes con el grafo.
    assert modelo.check_model(), "Error de consistencia en el modelo pgmpy."
    return VariableElimination(modelo)


def consultar_pgmpy(
    motor_pgmpy: VariableElimination,
    variable_consulta: str,
    evidencia: Dict[str, bool],
) -> Dict[bool, float]:
    """
    Ejecuta inferencia exacta mediante Eliminacion de Variables en pgmpy.
    """
    # Si la variable consultada ya forma parte de la evidencia, su posterior es determinista
    if variable_consulta in evidencia:
        val = evidencia[variable_consulta]
        return {True: 1.0 if val else 0.0, False: 0.0 if val else 1.0}

    resultado = motor_pgmpy.query(
        variables=[variable_consulta], evidence=evidencia, show_progress=False
    )
    # values[0] corresponde a False y values[1] a True.
    return {
        False: float(resultado.values[0]),
        True: float(resultado.values[1]),
    }
