"""Metadata extractors and the ingestion pipeline (TASK-01 / TASK-09)."""

from metatracer.extractors.crawler import FetchedPage, PublicDocCrawler
from metatracer.extractors.fields import ExtractedField
from metatracer.extractors.headers import extract_http_headers
from metatracer.extractors.html import HtmlMetadataExtractor
from metatracer.extractors.image import ImageMetadataExtractor
from metatracer.extractors.ingest import IngestionPipeline, IngestionSummary
from metatracer.extractors.javascript import JavaScriptMetadataExtractor
from metatracer.extractors.pdf import PdfMetadataExtractor
from metatracer.extractors.sniff import AssetKind, classify_downloaded_asset, sniff_asset_kind
from metatracer.extractors.targets import ResolvedTarget, TargetKind, TargetResolver

__all__ = [
    "AssetKind",
    "ExtractedField",
    "FetchedPage",
    "HtmlMetadataExtractor",
    "ImageMetadataExtractor",
    "IngestionPipeline",
    "IngestionSummary",
    "JavaScriptMetadataExtractor",
    "PdfMetadataExtractor",
    "PublicDocCrawler",
    "ResolvedTarget",
    "TargetKind",
    "TargetResolver",
    "classify_downloaded_asset",
    "extract_http_headers",
    "sniff_asset_kind",
]
