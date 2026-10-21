"""
define the valid data shape for the extracted BOM data using Pydantic models
"""
import re
from pydantic import BaseModel, ConfigDict, Field, model_validator


# Purpose: Base class for every data shape in the app. It rejects unexpected fields and strips whitespace from text.
# Input: the data to validate, as a dict or keyword arguments.
# Output: a validated model instance; raises a validation error when a field is unknown or invalid.
class StrictModel(BaseModel):
    """
    Base model that forbids extra fields and strips whitespace from string fields.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# Purpose: One colorway entry of a material: which garment colorway it belongs to and the material colour used there.
# Input: code and name of the garment colorway, material_color_code and material_color_name, fabric_reference (all optional text).
# Output: a validated Colorway; missing values stay None, never guessed.
class Colorway(StrictModel):
    """
    colorways table contains the extracted colorway data from the BOM
    """
    code: str | None = None
    name: str | None = None
    material_color_code: str | None = None
    material_color_name: str | None = None
    fabric_reference: str | None = None


# Purpose: One row of the Wovens bill of materials: a material with its quantity, unit and per-colorway details.
# Input: material_code, description, composition, placement, quantity (exact text), unit, a list of Colorway items and source_pages.
# Output: a validated Material. A quantity printed with its unit, such as '0.95 m', is split into quantity and unit automatically.
class Material(StrictModel):
    """
    materials table contains the extracted material data from the BOM
    """
    material_code: str | None = None
    description: str | None = None
    composition: str | None = None
    placement: str | None = None
    quantity: str | None = None  # Exact numeric text, e.g. '0.95'; never guess.
    unit: str | None = None      # m, kg, pcs, etc. Preserve unit as printed.
    colorways: list[Colorway] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)


    @model_validator(mode="before")
    @classmethod
    def separate_quantity_unit(cls, value):
        """
        Purpose: Validator that runs before a Material is created. It splits a quantity printed with
        its unit, such as '0.95 m', into quantity '0.95' and unit 'm'.
        Input: value - the raw data for the Material (normally a dict).
        Output: the data with quantity and unit separated, or unchanged when the quantity has no
        recognized unit or the printed unit conflicts with the unit already given.
        """
        if isinstance(value, dict) and isinstance(value.get("quantity"), str):
            match = re.fullmatch(
                r"\s*([+-]?\d+(?:[.,]\d+)?)\s*(mm|cm|m|kg|g|pcs|pc|yd|yards?)\s*",
                value["quantity"], re.IGNORECASE,
            )
            if match and (not value.get("unit") or value["unit"].strip().casefold() == match[2].casefold()):
                value = {**value, "quantity": match[1], "unit": value.get("unit") or match[2]}
        return value


# Purpose: A colorway column heading printed above the BOM table (a 4-digit code and its name).
# Input: code and name (optional text).
# Output: a validated ColorwayHeader, used to give every row's colorways the same names.
class ColorwayHeader(StrictModel):
    """
    colorway_headers table contains the extracted colorway header data from the BOM
    """
    code: str | None = None
    name: str | None = None


# Purpose: What the model returns for one Tech Pack page: whether it has a Wovens BOM, and the rows found.
# Input: section_found (required), style_number, tech_pack_number, materials, colorway_headers and warnings.
# Output: a validated PageResult. This class is also sent to the model as the required reply format.
class PageResult(StrictModel):
    """
    page_results table contains the extracted BOM data for each page of the techpack document.
    """
    section_found: bool
    style_number: str | None = None
    tech_pack_number: str | None = None
    materials: list[Material] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    colorway_headers: list[ColorwayHeader] = Field(default_factory=list)


# Purpose: The model's yes/no answer to "does this page contain a Wovens BOM table?".
# Input: has_wovens_bom (true or false).
# Output: a validated PageClassify, used to decide which unclear pages to extract.
class PageClassify(StrictModel):
    """
    page_classifications table contains the classification of each page of the techpack document.
    """
    has_wovens_bom: bool


# Purpose: The Wovens table of one PDF page, kept as its own table for display and correction.
# Input: page_number, materials and colorway_headers.
# Output: a validated WovensPageTable.
class WovensPageTable(StrictModel):
    """
    that represents the wovens bom table from one page of the techpack document. 
    it keeps that page's material rows and colorway headings together
    """
    page_number: int
    materials: list[Material] = Field(default_factory=list)
    colorway_headers: list[ColorwayHeader] = Field(default_factory=list)


# Purpose: The complete extracted result for one Tech Pack: combined materials, per-page tables, warnings and token usage.
# Input: style_number, tech_pack_number, category, materials, source_pages, warnings, page_tables and request_usage.
# Output: a validated DocumentExtraction, which is what gets saved in the database and edited by the user.
class DocumentExtraction(StrictModel):
    """
    represents the complete extracted BOM result for a single techpack document
    """
    style_number: str | None = None
    tech_pack_number: str | None = None
    category: str = "Wovens"
    materials: list[Material] = Field(default_factory=list)
    source_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    page_tables: list[WovensPageTable] = Field(default_factory=list)
    request_usage: list[dict] = Field(default_factory=list)
