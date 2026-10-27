"""The application as a whole: API, health check, and the built frontend."""
from fastapi.testclient import TestClient

from egc27demo.main import create_app

from .test_experiment_api import write_experiment


def test_the_api_answers_from_the_data_folder(tmp_path):
    client = TestClient(create_app(data_dir=write_experiment(tmp_path), frontend_dist=None))

    assert client.get("/api/experiment").json()["sizes"] == [2]
    assert client.get("/health").json() == {"status": "ok", "data": True}


def test_health_tells_when_the_data_is_missing(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path / "none", frontend_dist=None))
    assert client.get("/health").json()["data"] is False


def test_a_built_frontend_is_served_beside_the_api(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<title>Demo EGC27</title>")
    client = TestClient(create_app(data_dir=write_experiment(tmp_path), frontend_dist=dist))

    assert "Demo EGC27" in client.get("/").text
    assert client.get("/api/experiment").status_code == 200


def test_without_a_build_only_the_api_is_served(tmp_path):
    client = TestClient(create_app(data_dir=write_experiment(tmp_path), frontend_dist=tmp_path / "nothing"))
    assert client.get("/").status_code == 404
