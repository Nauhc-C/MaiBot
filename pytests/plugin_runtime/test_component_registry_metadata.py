from src.plugin_runtime.component_query import ComponentQueryService
from src.plugin_runtime.host.component_registry import ComponentRegistry, ToolEntry


def test_register_plugin_components_flattens_nested_metadata_visibility() -> None:
    registry = ComponentRegistry()

    registry.register_plugin_components(
        "test.plugin",
        [
            {
                "name": "visible_tool",
                "component_type": "tool",
                "metadata": {
                    "description": "visible tool",
                    "enabled": True,
                    "metadata": {
                        "visibility": "visible",
                    },
                },
            }
        ],
    )

    component = registry.get_component("test.plugin.visible_tool")

    assert isinstance(component, ToolEntry)
    assert component.metadata["visibility"] == "visible"
    assert ComponentQueryService._get_tool_visibility(component) == "visible"
