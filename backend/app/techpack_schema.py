"""
define the valid data shape for the extracted BOM data using Pydantic models
"""
import re
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """
    Base model that forbids extra fields and strips whitespace from string fields.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Colorway(StrictModel):
    """
    colorways table contains the extracted colorway data from the BOM
    """
    code: str | None = None
    name: str | None = None
    material_color_code: str | None = None
    material_color_name: str | None = None
    fabric_reference: str | None = None


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


    """
    that funtion is a model validator that is used to separate the quantity and unit from a single string field into 2 separate fields.
    it will run before the model is created 
    """
    @model_validator(mode="before")
    @classmethod
    def separate_quantity_unit(cls, value):
        if isinstance(value, dict) and isinstance(value.get("quantity"), str):
            match = re.fullmatch(
                r"\s*([+-]?\d+(?:[.,]\d+)?)\s*(mm|cm|m|kg|g|pcs|pc|yd|yards?)\s*",
                value["quantity"], re.IGNORECASE,
            )
            if match and (not value.get("unit") or value["unit"].strip().casefold() == match[2].casefold()):
                value = {**value, "quantity": match[1], "unit": value.get("unit") or match[2]}
        return value


class ColorwayHeader(StrictModel):
    """
    colorway_headers table contains the extracted colorway header data from the BOM
    """
    code: str | None = None
    name: str | None = None


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


class PageClassify(StrictModel):
    """
    page_classifications table contains the classification of each page of the techpack document.
    """
    has_wovens_bom: bool


class WovensPageTable(StrictModel):
    """
    that represents the wovens bom table from one page of the techpack document. 
    it keeps that page's material rows and colorway headings together
    """
    page_number: int
    materials: list[Material] = Field(default_factory=list)
    colorway_headers: list[ColorwayHeader] = Field(default_factory=list)


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
