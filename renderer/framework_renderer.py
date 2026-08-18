from models.automation import AutomationModel
from renderer.api_client_renderer import render_api_client
from renderer.data_renderer import render_data
from renderer.models import FrameworkManifest, RendererConventions
from renderer.page_object_renderer import render_page_objects
from renderer.scaffold_renderer import render_scaffold
from renderer.test_renderer import render_tests


def render_framework(
    model: AutomationModel, conventions: RendererConventions
) -> FrameworkManifest:
    """Composition root: AutomationModel -> FrameworkManifest.

    Thin by design (see .docs/architecture.md, "Renderer is a layer of
    per-artifact renderers, not a God class") - it only slices the model
    for each per-artifact renderer and concatenates their outputs. Every
    "should I emit anything for empty input" decision belongs to the
    individual renderer (e.g. render_api_client/render_tests already
    return [] when there are no operations/scenarios) and must stay there.
    """
    artifacts = [
        *render_scaffold(conventions),
        *render_page_objects(model.screens, model.scenarios, conventions),
        *render_api_client(model.operations, model.data_profiles, conventions),
        *render_data(model.data_profiles, conventions),
        *render_tests(
            model.scenarios,
            model.screens,
            model.operations,
            model.data_profiles,
            conventions,
        ),
    ]
    return FrameworkManifest(artifacts=artifacts)
