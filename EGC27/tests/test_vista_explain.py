"""Tests de l'extraction du raisonnement de VISTA."""
import json

import pandas as pd

from EGC27.vista_explain import clean_rule, explain_results, parse_support, split_resolution, write_explanations

VB = {"vb_1": {"speed_profile": "stable", "course_change": "slight turn to the right", "intent": "navigating",
               "duration": "100~150", "llm_output": "'''raw'''"}}
VF = {"vf_1": {"description": "Linear path.", "code": "def spatial_function(start, end, Time_interval):\n    return []"}}


def entry(seq, seg, mmsi=111, ok=True):
    if not ok:
        return {"sequence_id": seq, "segment_id": seg, "mmsi": mmsi,
                "behavior_estimator": None, "method_selector": None, "explanation_composer": None}
    return {
        "sequence_id": seq, "segment_id": seg, "mmsi": mmsi,
        "behavior_estimator": {
            "selected_movement_id": "vb_1",
            "graph_support": "vb_1 [w=5], vs_vessel_type_Cargo [w=2], vs_length_[150, 200) m [w=1]",
            "contextual_justification": "Consistent with neighbours.\n'''\n\n[resolution] The model answered '4', read as index 4.",
        },
        "method_selector": {
            "selected_function_id": "vf_1",
            "statistical_support": "95% likely.\n\n[resolution] The model answered '0'.",
            "reasoning": "Fits a stable speed.",
        },
        "explanation_composer": {
            "operational_protocol_rationale": "Typical of a cargo vessel.\n'''",
            "regulatory_rule_cue": "Undetermined; leave Undetermined if insufficient\nOperational Protocol Rationale: …",
        },
    }


INDEX = pd.DataFrame({"sequence_id": [0, 1], "segment_id": [3, 4], "gap_id": ["111_c4", "222_c4"]})


def test_each_gap_gets_its_own_segments_reasoning():
    results = [entry(0, 2), entry(0, 3), {}, entry(1, 4, 222, ok=False)]
    ex = explain_results(results, VB, VF, INDEX)

    assert set(ex) == {"111_c4", "222_c4"}
    assert ex["111_c4"]["status"] == "ok"
    assert ex["222_c4"] == {"status": "failed", "behaviour": None, "function": None, "explanation": None}


def test_a_gap_without_any_result_is_a_failure():
    assert explain_results([], VB, VF, INDEX)["111_c4"]["status"] == "failed"


def test_behaviour_comes_with_its_graph_attributes_and_support():
    b = explain_results([entry(0, 3)], VB, VF, INDEX)["111_c4"]["behaviour"]

    assert b["attributes"] == {"speed_profile": "stable", "course_change": "slight turn to the right",
                               "intent": "navigating", "duration": "100~150"}
    assert [s["node"] for s in b["support"]] == ["vb_1", "vs_vessel_type_Cargo", "vs_length_[150, 200) m"]
    assert [s["weight"] for s in b["support"]] == [5, 2, 1]


def test_the_resolution_note_is_kept_apart_from_the_reasoning():
    b = explain_results([entry(0, 3)], VB, VF, INDEX)["111_c4"]["behaviour"]

    assert b["justification"] == "Consistent with neighbours."
    assert b["resolution"].startswith("The model answered '4'")


def test_function_carries_its_code_and_why_it_was_chosen():
    f = explain_results([entry(0, 3)], VB, VF, INDEX)["111_c4"]["function"]

    assert f["code"].startswith("def spatial_function")
    assert f["statistical_support"] == "95% likely."
    assert f["reasoning"] == "Fits a stable speed."


def test_explanation_is_cleaned_of_the_models_leftovers():
    e = explain_results([entry(0, 3)], VB, VF, INDEX)["111_c4"]["explanation"]

    assert e["operational"] == "Typical of a cargo vessel."
    assert e["regulatory"] == "Undetermined"


def test_free_form_support_is_kept_as_text():
    free = entry(0, 3)
    free["behavior_estimator"]["graph_support"] = "The movement has the highest weight for Cargo (w=2)."
    b = explain_results([free], VB, VF, INDEX)["111_c4"]["behaviour"]

    assert b["support"] == []
    assert b["support_text"].startswith("The movement has")


def test_missing_graph_nodes_do_not_break_the_extraction():
    ex = explain_results([entry(0, 3)], {}, {}, INDEX)["111_c4"]
    assert ex["behaviour"]["attributes"] == {}
    assert ex["function"]["code"] is None


def test_small_helpers():
    assert parse_support(None) == []
    assert split_resolution(None) == (None, None)
    assert clean_rule("COLREG rule 8 '''") == "COLREG rule 8"


def test_written_from_the_latest_checkpoint(tmp_path):
    root = tmp_path / "EGC27_c4"
    (root / "ImputationResults").mkdir(parents=True)
    (root / "SDKG").mkdir()
    (root / "ImputationResults" / "imputation_results_trajectory40_len200_seed42_40_2.json").write_text(json.dumps([]))
    (root / "ImputationResults" / "imputation_results_trajectory40_len200_seed42_40_40.json").write_text(json.dumps([entry(0, 3)]))
    (root / "SDKG" / "SDK_graph_vb_node_8.json").write_text(json.dumps({"SDK_graph_vb_node": {}}))
    (root / "SDKG" / "SDK_graph_vb_node_40.json").write_text(json.dumps({"SDK_graph_vb_node": VB}))
    (root / "SDKG" / "SDK_graph_vf_node_40.json").write_text(json.dumps({"SDK_graph_vf_node": VF}))
    dest = tmp_path / "vista_c4_explanations.json"

    write_explanations(root, INDEX, dest)
    written = json.loads(dest.read_text())

    assert written["111_c4"]["status"] == "ok"
    assert written["111_c4"]["behaviour"]["attributes"]["intent"] == "navigating"
