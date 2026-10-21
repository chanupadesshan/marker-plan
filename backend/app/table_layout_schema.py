"""Small layout-only response for tables without visible full-width rules."""
from pydantic import Field
from .techpack_schema import StrictModel


# Purpose: The model's answer when asked where a table can be split between rows (layout only, no cell data).
# Input: row_cuts - vertical positions from 0 to 1000 (fractions of the page height) of gaps between complete rows.
# Output: a validated TableRowLayout; the positions are checked against real whitespace before use.
class TableRowLayout(StrictModel):
    row_cuts: list[int] = Field(default_factory=list, description=
        'Vertical positions between complete logical table rows, normalized to 0..1000 of full image height')
