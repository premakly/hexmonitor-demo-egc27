"""The static export: the same answers as the API, as files."""
import json

import pytest
from fastapi.testclient import TestClient

from egc27demo.export_static import export, gap_file, main
from egc27demo.main import create_app
from egc27demo.experiment_store import ExperimentStore

from .test_experiment_api import write_experiment


@pytest.fixture
def exported(tmp_path):
    data = write_experiment(tmp_path)
    out = tmp_path / "static"
    counts = export(ExperimentStore(data), out)
    client = TestClient(create_app(data_dir=data, frontend_dist=None))
    return out, counts, client


def read(path):
    return json.loads(path.read_text())


def test_overview_and_gap_list_match_the_api(exported):
    out, _, client = exported

    assert read(out / "overview.json") == client.get("/api/experiment").json()
    assert read(out / "gaps.json") == client.get("/api/experiment/gaps").json()


def test_every_gap_has_its_own_file_matching_the_api(exported):
    out, counts, client = exported

    assert counts["gaps"] == 2
    for gap_id in ("111_c2", "222_c2"):
        assert read(out / "gaps" / gap_file(gap_id)) == client.get(f"/api/experiment/gaps/{gap_id}").json()


def test_tables_are_copied_for_download(exported):
    out, counts, client = exported

    assert counts["exports"] == 2
    assert (out / "export" / "summary.csv").read_text() == client.get("/api/experiment/export/summary.csv").text


def test_a_gap_id_is_made_safe_for_a_file_name():
    assert gap_file("111_c2") == "111_c2.json"
    assert gap_file("a/b c") == "a%2Fb%20c.json"


def test_a_new_export_leaves_nothing_of_the_previous_one(tmp_path):
    data = write_experiment(tmp_path)
    out = tmp_path / "static"
    (out / "gaps").mkdir(parents=True)
    (out / "gaps" / "removed_gap.json").write_text("{}")
    export(ExperimentStore(data), out)

    assert not (out / "gaps" / "removed_gap.json").exists()


def test_the_command_refuses_a_folder_without_data(tmp_path):
    with pytest.raises(SystemExit, match="no experiment data"):
        main(["--data", str(tmp_path / "none"), "--out", str(tmp_path / "out")])


def test_the_command_writes_where_asked(tmp_path, capsys):
    data = write_experiment(tmp_path)
    main(["--data", str(data), "--out", str(tmp_path / "out")])

    assert (tmp_path / "out" / "overview.json").exists()
    assert "2 gaps and 2 tables" in capsys.readouterr().out
