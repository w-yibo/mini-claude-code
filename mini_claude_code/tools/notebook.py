"""
Notebook Edit tool.
Maps to: src/tools/NotebookEditTool/

Edit Jupyter notebook cells — replace, insert, or delete.
"""

import json
from pathlib import Path

from . import ToolSpec


def run_notebook_edit(inp: dict) -> str:
    notebook_path = inp.get("notebook_path", "")
    new_source = inp.get("new_source", "")
    cell_number = inp.get("cell_number", 0)
    cell_type = inp.get("cell_type", "code")
    edit_mode = inp.get("edit_mode", "replace")

    if not notebook_path:
        return "Error: notebook_path is required"

    try:
        path = Path(notebook_path).expanduser().resolve()
        if not path.exists():
            return f"Error: notebook not found: {notebook_path}"

        with open(path) as f:
            nb = json.load(f)

        cells = nb.get("cells", [])

        if edit_mode == "insert":
            new_cell = {
                "cell_type": cell_type,
                "metadata": {},
                "source": new_source.splitlines(True),
                "outputs": [] if cell_type == "code" else None,
            }
            if cell_type == "code":
                new_cell["execution_count"] = None
            else:
                del new_cell["outputs"]  # markdown cells don't have outputs
            cells.insert(cell_number, new_cell)

        elif edit_mode == "delete":
            if cell_number < 0 or cell_number >= len(cells):
                return f"Error: cell_number {cell_number} out of range (0-{len(cells) - 1})"
            cells.pop(cell_number)

        else:  # replace
            if cell_number < 0 or cell_number >= len(cells):
                return f"Error: cell_number {cell_number} out of range (0-{len(cells) - 1})"
            cells[cell_number]["source"] = new_source.splitlines(True)
            if cell_type:
                cells[cell_number]["cell_type"] = cell_type

        nb["cells"] = cells

        with open(path, "w") as f:
            json.dump(nb, f, indent=1, ensure_ascii=False)
            f.write("\n")

        return f"Successfully {edit_mode}d cell {cell_number} in {notebook_path}"
    except json.JSONDecodeError:
        return f"Error: {notebook_path} is not a valid JSON notebook"
    except Exception as e:
        return f"Error: {e}"


spec = ToolSpec(
    name="NotebookEdit",
    description=(
        "Edit Jupyter notebook (.ipynb) cells. "
        "Supports replace, insert, and delete operations on individual cells."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "notebook_path": {"type": "string", "description": "Path to the .ipynb file"},
            "cell_number": {"type": "integer", "description": "Cell index (0-based)"},
            "new_source": {"type": "string", "description": "New cell source content"},
            "cell_type": {
                "type": "string",
                "description": "Cell type: 'code' or 'markdown'",
                "enum": ["code", "markdown"],
            },
            "edit_mode": {
                "type": "string",
                "description": "Edit mode: replace, insert, or delete",
                "enum": ["replace", "insert", "delete"],
                "default": "replace",
            },
        },
        "required": ["notebook_path", "new_source"],
    },
    run=run_notebook_edit,
)
