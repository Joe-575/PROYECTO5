"""
Modulo de verificacion cruzada mediante la biblioteca pgmpy (Eliminacion de Variables).
"""

from typing import Dict
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination

try:
    from pgmpy.models import DiscreteBayesianNetwork as BayesianNetwork
except ImportError:
    from pgmpy.models import BayesianNetwork

from inferencia_bayesiana import RedBayesiana


def construir_modelo_pgmpy(red: RedBayesiana) -> VariableElimination:
    """
    Traduce dinamicamente el objeto RedBayesiana al formato de pgmpy.
    """
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
            p_true = float(cpt[""])
            cpd = TabularCPD(
                variable=var,
                variable_card=2,
                values=[[1.0 - p_true], [p_true]],
                state_names={var: [False, True]},
            )
        else:
            # Orden de columnas en pgmpy: combinaciones booleanas en orden lexicografico
            num_combinaciones = 2 ** len(padres)
            probs_false = []
            probs_true = []

            for i in range(num_combinaciones):
                bits = [(i >> (len(padres) - 1 - k)) & 1 for k in range(len(padres))]
                clave = ",".join("true" if b == 1 else "false" for b in bits)
                p_t = float(cpt[clave])
                probs_true.append(p_t)
                probs_false.append(1.0 - p_t)

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
    return {
        False: float(resultado.values[0]),
        True: float(resultado.values[1]),
    }