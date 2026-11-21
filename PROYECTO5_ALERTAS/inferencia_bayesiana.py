"""
Motor propio de inferencia exacta por enumeracion para Redes Bayesianas binarias.
No utiliza bibliotecas externas de inferencia probabilistica.
"""

import json
import copy
from typing import Dict, List


class RedBayesiana:
    def __init__(self, ruta_json: str = None, datos: dict = None):
        # La red se carga desde un archivo JSON o desde un diccionario ya leido.
        # Con 'datos' se hace una copia profunda para no compartir memoria.
        if datos is not None:
            self.datos = copy.deepcopy(datos)
        elif ruta_json is not None:
            with open(ruta_json, "r", encoding="utf-8") as archivo:
                self.datos = json.load(archivo)
        else:
            raise ValueError("Debe proporcionar 'ruta_json' o 'datos'.")

        # Descripciones, orden de procesamiento (padres antes que hijos) y CPT.
        self.variables: Dict[str, str] = self.datos["variables"]
        self.orden_topologico: List[str] = self.datos["orden_topologico"]
        self.nodos: Dict[str, dict] = self.datos["nodos"]

    def probabilidad_condicional(
        self, variable: str, valor: bool, asignacion: Dict[str, bool]
    ) -> float:
        """
        Retorna P(variable = valor | padres(variable) segun asignacion).
        """
        nodo = self.nodos[variable]
        padres = nodo["padres"]

        # La clave de la CPT es la combinacion de valores de los padres
        # (por ejemplo "true,false"); los nodos raiz usan la clave vacia.
        if not padres:
            clave = ""
        else:
            clave = ",".join("true" if asignacion[p] else "false" for p in padres)

        # El JSON solo guarda P(True); P(False) es su complemento.
        prob_true = float(nodo["cpt"][clave])
        return prob_true if valor else (1.0 - prob_true)

    def enumerate_all(
        self, variables: List[str], evidencia: Dict[str, bool]
    ) -> float:
        """
        Funcion recursiva ENUMERATE-ALL(vars, e):
        Calcula la suma de probabilidades conjuntas compatibles con 'evidencia'.
        """
        # Caso base: sin variables pendientes, el producto acumulado vale 1.
        if not variables:
            return 1.0

        primera = variables[0]
        resto = variables[1:]

        if primera in evidencia:
            # Valor conocido: solo se multiplica su probabilidad condicional.
            val = evidencia[primera]
            prob = self.probabilidad_condicional(primera, val, evidencia)
            return prob * self.enumerate_all(resto, evidencia)
        else:
            # Variable oculta: se suman las ramas True y False (marginalizacion).
            # Cada rama trabaja con su propia copia de la evidencia.
            suma_total = 0.0
            for val in (True, False):
                nueva_evidencia = evidencia.copy()
                nueva_evidencia[primera] = val
                prob = self.probabilidad_condicional(primera, val, nueva_evidencia)
                suma_total += prob * self.enumerate_all(resto, nueva_evidencia)
            return suma_total

    def enumeration_ask(
        self, variable_consulta: str, evidencia: Dict[str, bool]
    ) -> Dict[bool, float]:
        """
        Calcula la distribucion posterior normalizada P(X | e) mediante enumeracion.
        """
        if variable_consulta not in self.nodos:
            raise KeyError(f"Variable desconocida: {variable_consulta}")

        # Variable ya observada: su posterior es determinista. Sin esta guarda,
        # el bucle de abajo sobrescribiria el valor observado con True y False.
        if variable_consulta in evidencia:
            val = evidencia[variable_consulta]
            return {True: 1.0 if val else 0.0, False: 0.0 if val else 1.0}

        # Probabilidad conjunta (sin normalizar) para X=True y para X=False.
        distribucion: Dict[bool, float] = {}
        for val in (True, False):
            evidencia_extendida = evidencia.copy()
            evidencia_extendida[variable_consulta] = val
            distribucion[val] = self.enumerate_all(
                self.orden_topologico, evidencia_extendida
            )

        # Normalizacion: alfa = 1 / P(evidencia). Total 0 = evidencia imposible.
        total = sum(distribucion.values())
        if total == 0:
            raise ValueError("La evidencia proporcionada tiene probabilidad conjunta 0.")

        return {val: prob / total for val, prob in distribucion.items()}

    def actualizar_probabilidad_previa(self, variable: str, nueva_prob_true: float):
        """
        Permite modificar P(variable = True) para nodos raiz sin tocar el algoritmo.
        """
        if self.nodos[variable]["padres"]:
            raise ValueError(f"La variable {variable} no es un nodo raiz.")
        if not (0.0 <= nueva_prob_true <= 1.0):
            raise ValueError("La probabilidad debe estar en el rango [0, 1].")
        self.nodos[variable]["cpt"][""] = nueva_prob_true

    def clonar(self) -> "RedBayesiana":
        # Copia independiente: permite comparar previas sin alterar la red original.
        return RedBayesiana(datos=self.datos)
