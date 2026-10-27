"""Ce que VISTA a « pensé » pour chaque trou, extrait de ses propres résultats.

Pour chaque segment imputé, VISTA enregistre :
  - le comportement retenu (module M4) : un nœud de son graphe de
    connaissances (profil de vitesse, changement de cap, intention…), les
    nœuds qui l'appuient avec leur poids, et sa justification ;
  - la fonction choisie (module M5) : son code Python généré par le LLM, sa
    description, le support statistique et le raisonnement de ce choix ;
  - l'explication rédigée (module M6) : la justification opérationnelle et
    la règle réglementaire invoquée.

Ce module rassemble ces éléments par trou, sans rien recalculer, dans
<experiment_dir>/completions/vista_c{k}_explanations.json, que la vue
Expérience de Hex Monitor affiche.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

# A node name can itself hold commas and brackets (« vs_length_[150, 200) m »):
# a node runs up to the first « [w=…] » that follows it.
SUPPORT_ITEM = re.compile(r"\s*(?P<node>.+?)\s*\[w=(?P<weight>[\d.]+)\]\s*(?:,|$)")
RESOLUTION = re.compile(r"\s*\[resolution\]\s*(?P<note>.*)$", re.DOTALL)
CHECKPOINT = re.compile(r"_(\d+)(?:_(\d+))?\.json$")
BEHAVIOUR_FIELDS = ("speed_profile", "course_change", "heading_fluctuation", "intent", "duration")


def clean_text(text):
    """Retire les délimiteurs ''' que le LLM laisse autour de ses réponses."""
    if not isinstance(text, str):
        return None
    text = text.replace("'''", "").strip()
    return text or None


def clean_rule(text):
    """
    La règle réglementaire est souvent « Undetermined », suivie par erreur de
    la suite de la réponse du LLM : on ne garde alors que ce mot.
    """
    text = clean_text(text)
    if text and text.lower().startswith("undetermined"):
        return "Undetermined"
    return text


def split_resolution(text):
    """
    VISTA ajoute à la réponse du LLM une note sur la façon dont elle a été
    interprétée (« [resolution] The model answered '4', read as index 4… »).
    On la sépare du raisonnement lui-même.
    """
    text = clean_text(text)
    if not text:
        return None, None
    match = RESOLUTION.search(text)
    if not match:
        return text, None
    return clean_text(text[: match.start()]), clean_text(match["note"])


def parse_support(text) -> list[dict]:
    """« vb_x [w=5], vs_vessel_type_Cargo [w=2] » → [{node, weight}, …]."""
    if not isinstance(text, str):
        return []
    return [{"node": m["node"].strip(), "weight": float(m["weight"])} for m in SUPPORT_ITEM.finditer(text)]


def explain_entry(entry: dict | None, vb_nodes: dict, vf_nodes: dict) -> dict:
    if not entry or not entry.get("behavior_estimator") or not entry.get("method_selector"):
        return {"status": "failed", "behaviour": None, "function": None, "explanation": None}
    be, ms = entry["behavior_estimator"], entry["method_selector"]
    ep = entry.get("explanation_composer") or {}

    justification, resolution = split_resolution(be.get("contextual_justification"))
    vb_id = be.get("selected_movement_id")
    vb = vb_nodes.get(vb_id) or {}
    vf_id = ms.get("selected_function_id")
    vf = vf_nodes.get(vf_id) or {}
    return {
        "status": "ok",
        "behaviour": {
            "id": vb_id,
            "attributes": {k: clean_text(vb.get(k)) for k in BEHAVIOUR_FIELDS if vb.get(k)},
            # Structured when the LLM kept to the « node [w=n] » format; its
            # own wording otherwise, which varies from one answer to the next.
            "support": parse_support(be.get("graph_support")),
            "support_text": clean_text(be.get("graph_support")),
            "justification": justification,
            "resolution": resolution,
        },
        "function": {
            "id": vf_id,
            "description": clean_text(vf.get("description")),
            "code": vf.get("code"),
            "statistical_support": split_resolution(ms.get("statistical_support"))[0],
            "reasoning": clean_text(ms.get("reasoning")),
        },
        "explanation": {
            "operational": clean_text(ep.get("operational_protocol_rationale")),
            "regulatory": clean_rule(ep.get("regulatory_rule_cue")),
        },
    }


def explain_results(results: list, vb_nodes: dict, vf_nodes: dict, index: pd.DataFrame) -> dict:
    """Une explication par trou (gap_id), pour les seuls segments qui sont nos trous."""
    by_segment = {(e["sequence_id"], e["segment_id"]): e for e in results if e and "sequence_id" in e}
    return {
        row.gap_id: explain_entry(by_segment.get((row.sequence_id, row.segment_id)), vb_nodes, vf_nodes)
        for row in index.itertuples()
    }


def _latest(folder: Path, pattern: str) -> Path | None:
    """Le fichier du dernier point de reprise (plus grands numéros de fin de nom)."""
    files = [f for f in folder.glob(pattern) if CHECKPOINT.search(f.name)]
    if not files:
        return None

    def key(f):
        a, b = CHECKPOINT.search(f.name).groups()
        return (int(b) if b else int(a), int(a))

    return max(files, key=key)


def write_explanations(results_root: Path, index: pd.DataFrame, dest: Path) -> dict:
    """Lit les résultats d'une exécution de VISTA et écrit les explications par trou."""
    results_file = _latest(results_root / "ImputationResults", "imputation_results_*.json")
    vb_file = _latest(results_root / "SDKG", "SDK_graph_vb_node_*.json")
    vf_file = _latest(results_root / "SDKG", "SDK_graph_vf_node_*.json")
    results = json.loads(results_file.read_text()) if results_file else []
    vb = json.loads(vb_file.read_text()).get("SDK_graph_vb_node", {}) if vb_file else {}
    vf = json.loads(vf_file.read_text()).get("SDK_graph_vf_node", {}) if vf_file else {}

    explanations = explain_results(results, vb, vf, index)
    dest.write_text(json.dumps(explanations, indent=1, ensure_ascii=False))
    return explanations
