"""Small layout-only response for tables without visible full-width rules."""
from pydantic import Field
from .techpack_schema import StrictModel


class TableRowLayout(StrictModel):
    row_cuts: list[int] = Field(default_factory=list, description=
        'Vertical positions between complete logical table rows, normalized to 0..1000 of full image height')
