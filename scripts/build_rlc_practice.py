"""Build a small RLC teaching schematic from an empty Typhoon model.

Run with the Python bundled with Typhoon HIL Control Center 2026.3.
The output path must be a new file inside the project task directory.
"""

from pathlib import Path
import argparse
import json

from typhoon.api.schematic_editor import SchematicAPI


def build(destination: Path) -> dict:
    destination = destination.resolve()
    allowed = (Path(__file__).resolve().parents[1] / "results" / "agent-tasks").resolve()
    if not destination.is_relative_to(allowed) or destination.name != "rlc_handbuilt.tse":
        raise ValueError("practice output must be rlc_handbuilt.tse under results/agent-tasks")
    if destination.exists():
        raise FileExistsError(f"practice model already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    api = SchematicAPI()
    if api.create_new_model(name="RLC modeling practice") is False:
        raise RuntimeError("could not create a blank schematic")
    x, y = 8192, 8192
    parts = {
        "Vs1": api.create_component("core/Voltage Source", name="Vs1", position=(x - 400, y), rotation="right"),
        "Rin": api.create_component("core/Resistor", name="Rin", position=(x - 300, y - 100)),
        "I": api.create_component("core/Current Measurement", name="I", position=(x - 200, y - 100)),
        "L": api.create_component("core/Inductor", name="L", position=(x, y), rotation="right"),
        "R": api.create_component("core/Resistor", name="R", position=(x + 100, y - 100), rotation="right"),
        "C": api.create_component("core/Capacitor", name="C", position=(x + 100, y + 100), rotation="right"),
        "Va1": api.create_component("core/Voltage Measurement", name="Va1", position=(x + 250, y), rotation="right"),
        "V_Rin": api.create_component("core/Voltage Measurement", name="V_Rin", position=(x - 300, y - 250), rotation="right"),
        "gnd": api.create_component("core/Ground", name="gnd", position=(x - 400, y + 200)),
    }
    junctions = {
        "return": api.create_junction(name="J_return", position=(x - 400, y + 100)),
        "top": api.create_junction(name="J_top", position=(x, y - 100)),
        "bottom": api.create_junction(name="J_bottom", position=(x, y + 100)),
    }
    def term(name: str, pin: str):
        return api.term(parts[name], pin)
    connections = (
        (term("Vs1", "p_node"), term("Rin", "p_node")),
        (term("Vs1", "n_node"), junctions["return"]),
        (term("gnd", "node"), junctions["return"]),
        (term("Rin", "n_node"), term("I", "p_node")),
        (term("I", "n_node"), junctions["top"]),
        (junctions["top"], term("L", "p_node")),
        (term("L", "n_node"), junctions["bottom"]),
        (junctions["bottom"], junctions["return"]),
        (junctions["top"], term("R", "p_node")),
        (term("R", "n_node"), term("C", "p_node")),
        (term("C", "n_node"), junctions["bottom"]),
        (junctions["top"], term("Va1", "p_node")),
        (term("Va1", "n_node"), junctions["bottom"]),
        (term("Rin", "p_node"), term("V_Rin", "p_node")),
        (term("V_Rin", "n_node"), term("Rin", "n_node")),
    )
    for start, end in connections:
        if api.create_connection(start, end) is False:
            raise RuntimeError("failed to connect a schematic terminal")
    properties = (("Rin", "resistance", 5.0), ("R", "resistance", 0.1),
                  ("L", "inductance", 1e-5), ("C", "capacitance", 5e-4))
    for name, key, value in properties:
        if api.set_property_value(api.prop(parts[name], key), value) is False:
            raise RuntimeError(f"failed to set {name}.{key}")
    readback = {name: float(api.get_property_value(api.prop(parts[name], key)))
                for name, key, _ in properties}
    if any(readback[name] != value for name, _, value in properties):
        raise RuntimeError(f"parameter readback differs: {readback}")
    if api.save_as(filename=str(destination)) is False:
        raise RuntimeError("failed to save practice schematic")
    result = {"model": str(destination), "components": list(parts),
              "junctions": list(junctions), "connection_count": len(connections),
              "parameter_readback": readback}
    api.close_model()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=False, indent=2))
