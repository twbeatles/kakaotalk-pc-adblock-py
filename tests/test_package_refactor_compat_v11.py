import importlib


def test_app_package_preserves_expected_module_surface():
    app = importlib.import_module("kakao_adblocker.app")

    assert callable(app.main)
    assert callable(app.build_parser)
    assert hasattr(app, "os")
    assert hasattr(app, "sys")
    assert hasattr(app, "importlib")
    assert hasattr(app, "tk")
    assert hasattr(app, "LayoutOnlyEngine")
    assert hasattr(app, "TrayController")
    assert hasattr(app, "ProcessInspector")
    assert hasattr(app, "StartupManager")


def test_config_package_preserves_expected_module_surface():
    config = importlib.import_module("kakao_adblocker.config")

    assert hasattr(config, "APPDATA_DIR")
    assert hasattr(config, "SETTINGS_FILE")
    assert hasattr(config, "RULES_FILE")
    assert hasattr(config, "LOG_FILE")
    assert callable(config.resource_base_dir)
    assert callable(config.get_runtime_paths)
    assert callable(config.ensure_runtime_files)
    assert callable(config.consume_load_warnings)
    assert callable(config.LayoutSettingsV11.load)
    assert callable(config.LayoutRulesV11.load)


def test_event_engine_package_preserves_expected_module_surface():
    event_engine = importlib.import_module("kakao_adblocker.event_engine")

    assert hasattr(event_engine, "LayoutOnlyEngine")
    assert hasattr(event_engine, "EngineState")
    assert hasattr(event_engine, "WindowInfo")
    assert hasattr(event_engine, "time")
    assert hasattr(event_engine, "threading")
    assert hasattr(event_engine, "ProcessInspector")
