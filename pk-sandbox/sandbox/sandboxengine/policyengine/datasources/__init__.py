"""
Data source layer for external documents.

This module provides an abstract interface for reading/writing external documents
(Google Sheets, Notion, etc.) in governance policies.

Main exports:
- DataSource: Abstract base class
- DocumentSchema: Document structure descriptor
- DataSourceRegistry: Manage data source instances
- InMemoryDataSource: In-memory mock for testing
"""

from .base import DataSource, DocumentSchema, DataSourceRegistry
from .mock import InMemoryDataSource

__all__ = [
    "DataSource",
    "DocumentSchema",
    "DataSourceRegistry",
    "InMemoryDataSource",
]
