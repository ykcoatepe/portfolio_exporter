import importlib
import pkgutil

import portfolio_exporter.scripts as scripts_pkg


def _parsers():
    for modinfo in pkgutil.iter_modules(scripts_pkg.__path__):
        if modinfo.ispkg:
            continue
        try:
            module = importlib.import_module(
                f"{scripts_pkg.__name__}.{modinfo.name}"
            )
        except Exception:
            continue
        if hasattr(module, "get_arg_parser"):
            yield modinfo.name, module.get_arg_parser()


def test_common_flags_present():
    required = {"--json", "--no-pretty", "--no-files", "--output-dir"}
    found_daily_report = False
    for name, parser in _parsers():
        opts = set(parser._option_string_actions)
        assert required <= opts, f"{name} missing common flags"
        if name == "daily_report":
            assert "--excel" in opts
            found_daily_report = True
    assert found_daily_report, "daily_report parser not discovered"
