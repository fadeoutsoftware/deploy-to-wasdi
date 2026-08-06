import sys
import types

import pytest

from deploy_to_wasdi import cli


@pytest.fixture(autouse=True)
def reset_cli_state():
    cli._WASDI_INITIALIZED = False
    cli._DEPLOYED_PROCESSORS_CACHE = None
    yield
    cli._WASDI_INITIALIZED = False
    cli._DEPLOYED_PROCESSORS_CACHE = None


def test_parser_accepts_config_before_or_after_subcommand():
    parser = cli.create_parser()

    assert parser.parse_args(["prepare"]).config == "deploy_config.yaml"
    assert parser.parse_args(["-c", "before.yaml", "prepare"]).config == "before.yaml"
    assert parser.parse_args(["prepare", "-c", "after.yaml"]).config == "after.yaml"


def test_prepare_resolves_paths_relative_to_config_file(tmp_path, monkeypatch):
    config_dir = tmp_path / "project"
    source_dir = config_dir / "application"
    source_dir.mkdir(parents=True)
    (source_dir / "app.py").write_text("print('processor')\n")
    shared_module = config_dir / "shared.py"
    shared_module.write_text("VALUE = 1\n")
    config_path = config_dir / "deploy.yaml"
    config_path.write_text(
        "\n".join(
            [
                "project_name: processor",
                "build_dir: build",
                "source_dir: application",
                "custom_modules:",
                "  - shared.py",
                "entry_point:",
                "  source: app.py",
                "  target: myProcessor.py",
            ]
        )
    )
    other_directory = tmp_path / "other"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)

    cli.prepare_deployment(str(config_path))

    build_dir = config_dir / "build"
    assert (build_dir / "myProcessor.py").exists()
    assert (build_dir / "shared.py").exists()
    assert (build_dir / "processor.zip").exists()


@pytest.mark.parametrize("command", [cli.update_to_wasdi, cli.update_params])
def test_existing_processor_commands_initialize_wasdi(tmp_path, monkeypatch, command):
    config_path = tmp_path / "deploy.yaml"
    config_path.write_text(
        "\n".join(
            [
                "project_name: processor",
                "build_dir: build",
                "workspace_id: workspace",
                "params_sample: '{}'",
            ]
        )
    )
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "processor.zip").write_bytes(b"archive")
    initialized = []
    requests = types.SimpleNamespace(
        post=lambda *args, **kwargs: types.SimpleNamespace(status_code=200, text="", json=lambda: {})
    )
    wasdi = types.SimpleNamespace(
        getBaseUrl=lambda: "https://wasdi.example",
        getSessionId=lambda: "session",
    )
    monkeypatch.setitem(sys.modules, "requests", requests)
    monkeypatch.setitem(sys.modules, "wasdi", wasdi)
    monkeypatch.setattr(cli, "init_wasdi", lambda config, config_dir: initialized.append(config_dir))
    monkeypatch.setattr(cli, "get_processor_info", lambda config_file: {"processorId": "processor-id"})

    command(str(config_path))

    assert initialized == [tmp_path]