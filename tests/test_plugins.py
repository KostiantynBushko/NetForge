"""The plugin system."""

from __future__ import annotations

import textwrap

from netforge.plugins.base import Plugin
from netforge.plugins.manager import PluginManager

PLUGIN_SOURCE = textwrap.dedent(
    '''
    """A plugin that adds one operation."""

    from netforge.core.operation import Operation
    from netforge.models.base import RequestModel, ResponseModel
    from netforge.models.capability import CapabilityCategory
    from netforge.models.risk import RiskLevel
    from netforge.plugins.base import Plugin


    class WidgetRequest(RequestModel):
        """A request."""

        size: int = 1


    class WidgetResponse(ResponseModel):
        """A response."""

        size: int = 1


    class WidgetOperation(Operation):
        """A widget operation."""

        name = "plugin.widget"
        category = CapabilityCategory.DISCOVERY
        risk_level = RiskLevel.SAFE
        summary = "A widget."
        request_model = WidgetRequest
        response_model = WidgetResponse

        async def execute(self, request, context):
            """Do nothing."""
            return WidgetResponse(size=request.size)


    class WidgetPlugin(Plugin):
        """A plugin that adds the widget operation."""

        name = "widget"
        version = "1.2.3"
        description = "Adds the widget operation."

        def operations(self):
            """Return the operations of the plugin."""
            return [WidgetOperation]
    '''
)

BROKEN_PLUGIN_SOURCE = textwrap.dedent(
    '''
    """A plugin that cannot be imported."""

    raise RuntimeError("this plugin is broken")
    '''
)


def _write_plugin(directory, name: str, source: str) -> None:
    package = directory / name
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(source, encoding="utf-8")


class TestPluginLoading:
    def test_a_plugin_directory_is_loaded(self, tmp_path):
        _write_plugin(tmp_path, "widget_plugin", PLUGIN_SOURCE)

        manager = PluginManager()
        loaded = manager.load_directory(tmp_path)

        assert len(loaded) == 1
        assert loaded[0].name == "widget"
        assert loaded[0].version == "1.2.3"

    def test_the_operations_of_a_plugin_are_registered(self, tmp_path):
        _write_plugin(tmp_path, "widget_plugin", PLUGIN_SOURCE)

        manager = PluginManager()
        manager.load_all(directories=[tmp_path])

        assert "plugin.widget" in manager.registry
        descriptor = manager.registry.get("plugin.widget")
        assert descriptor.summary == "A widget."

    def test_a_broken_plugin_is_reported_and_does_not_stop_the_load(self, tmp_path):
        _write_plugin(tmp_path, "broken_plugin", BROKEN_PLUGIN_SOURCE)
        _write_plugin(tmp_path, "widget_plugin", PLUGIN_SOURCE)

        manager = PluginManager()
        manager.load_all(directories=[tmp_path])

        assert manager.failures
        assert any("broken_plugin" in failure["source"] for failure in manager.failures)
        assert "plugin.widget" in manager.registry

    def test_a_missing_directory_is_reported(self, tmp_path):
        manager = PluginManager()
        manager.load_directory(tmp_path / "absent")
        assert manager.failures

    def test_the_manager_describes_what_it_loaded(self, tmp_path):
        _write_plugin(tmp_path, "widget_plugin", PLUGIN_SOURCE)

        manager = PluginManager()
        manager.load_all(directories=[tmp_path])

        described = manager.describe()
        assert described[0]["name"] == "widget"
        assert described[0]["version"] == "1.2.3"


class TestPluginBase:
    def test_a_plugin_declares_itself(self):
        class EmptyPlugin(Plugin):
            """A plugin with no operations."""

            name = "empty"
            version = "0.1.0"
            description = "Nothing."

            def operations(self):
                """Return nothing."""
                return []

        assert EmptyPlugin().describe() == {
            "name": "empty",
            "version": "0.1.0",
            "description": "Nothing.",
        }

    def test_the_operations_must_be_operation_classes(self):
        class BadPlugin(Plugin):
            """A plugin with a bad operation."""

            name = "bad"

            def operations(self):
                """Return something that is not an operation."""
                return [str]

        manager = PluginManager()
        manager.register(BadPlugin())
        assert manager.failures
