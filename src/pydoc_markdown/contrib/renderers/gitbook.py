# -*- coding: utf-8 -*-

import dataclasses
import json
import logging
import os
import typing as t
from pathlib import Path

import databind.core.annotations as A
import docspec
import typing_extensions as te

from pydoc_markdown.contrib.renderers.markdown import MarkdownRenderer
from pydoc_markdown.interfaces import Context, Renderer
from pydoc_markdown.util.docspec import ApiSuite, format_function_signature, is_method

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class CustomizedMarkdownRenderer(MarkdownRenderer):
    """We override some defaults in this subclass."""

    header_level_by_type: t.Dict[str, int] = dataclasses.field(
        default_factory=lambda: {
            "Class": 1,
            "Method": 2,
            "Function": 2,
            "Variable": 2,
        }
    )

    def _format_function_signature(
        self, func: docspec.Function, override_name: str = None, add_method_bar: bool = True
    ) -> str:
        parts: t.List[str] = []
        if self.signature_with_decorators:
            parts += self._format_decorations(func.decorations or [])
        if self.signature_python_help_style and not self._is_method(func):
            parts.append("{} = ".format(dotted_name(func)))
        parts += [x + " " for x in func.modifiers or []]
        if self.signature_with_def:
            parts.append("def ")
        if self.signature_class_prefix and self._is_method(func):
            parent = func.parent
            assert parent, func
            parts.append(parent.name + ".")
        parts.append((override_name or func.name))
        parts.append(format_function_signature(func, False))
        result = "".join(parts)
        result = self._yapf_code(result + ": pass").rpartition(":")[0].strip()

        if add_method_bar and self._is_method(func):
            result = "\n".join(" | " + l for l in result.split("\n"))
        return result

    def _format_arglist(self, func: docspec.Function) -> str:
        return format_arglist(func.args)


@dataclasses.dataclass
class GitBookRenderer(Renderer):
    """
    Produces Markdown files and a `sidebar.json` file for use in a [Docusaurus v2][1] websites.
    It creates files in a fixed layout that reflects the structure of the documented packages.
    The files will be rendered into the directory specified with the #docs_base_path option.

    Check out the complete [Docusaurus example on GitHub][2].

    [1]: https://v2.docusaurus.io/
    [2]: https://github.com/NiklasRosenstein/pydoc-markdown/tree/develop/examples/docusaurus

    ### Options
    """

    #: The #MarkdownRenderer configuration.
    markdown: te.Annotated[MarkdownRenderer, A.typeinfo(deserialize_as=CustomizedMarkdownRenderer)] = dataclasses.field(
        default_factory=CustomizedMarkdownRenderer
    )

    #: The path where the docusaurus docs content is. Defaults "docs" folder.
    docs_base_path: str = "docs"

    #: The output path inside the docs_base_path folder, used to output the
    #: module reference.
    relative_output_path: str = "reference"

    #: The sidebar path inside the docs_base_path folder, used to output the
    #: sidebar for the module reference.
    relative_sidebar_path: str = "sidebar.json"

    #: The top-level label in the sidebar. Default to 'Reference'. Can be set to null to
    #: remove the sidebar top-level all together. This option assumes that there is only one top-level module.
    sidebar_top_level_label: t.Optional[str] = "Reference"

    #: The top-level module label in the sidebar. Default to null, meaning that the actual
    #: module name will be used. This option assumes that there is only one top-level module.
    sidebar_top_level_module_label: t.Optional[str] = None

    def init(self, context: Context) -> None:
        self.markdown.init(context)

    def render(self, modules: t.List[docspec.Module]) -> None:
        module_tree: t.Dict[str, t.Any] = {"children": {}, "edges": []}
        output_path = Path(self.docs_base_path) / self.relative_output_path
        for module in modules:
            filepath = output_path

            module_parts = module.name.split(".")
            if module.location.filename.endswith("__init__.py"):
                module_parts.append("__init__")

            relative_module_tree = module_tree
            intermediary_module = []

            for module_part in module_parts[:-1]:
                # update the module tree
                intermediary_module.append(module_part)
                intermediary_module_name = ".".join(intermediary_module)
                relative_module_tree["children"].setdefault(intermediary_module_name, {"children": {}, "edges": []})
                relative_module_tree = relative_module_tree["children"][intermediary_module_name]

                # descend to the file
                filepath = filepath / module_part

            # create intermediary missing directories and get the full path
            filepath.mkdir(parents=True, exist_ok=True)
            filepath = filepath / f"{module_parts[-1]}.md"

            with filepath.open("w") as fp:
                logger.info("Render file %s", filepath)
                self.markdown.render_single_page(fp, [module])

            # only update the relative module tree if the file is not empty
            relative_module_tree["edges"].append(os.path.splitext(str(filepath.relative_to(self.docs_base_path)))[0])
