"""
Abstract data source layer for external documents.

PolicyKit equivalent: None (sandbox-specific)
Enables policies to read/write external documents (Google Sheets, Notion, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class DocumentSchema:
    """
    Describes the structure of an external document.

    Used for:
    1. LLM context during generation (what columns are available?)
    2. Test scenario setup (what data to mock?)
    3. Runtime validation (does written data match schema?)
    """
    source_type: str  # "google_sheets", "notion", "airtable"
    source_url: str
    structure: Dict[str, Any]  # columns, headers, sheet names, etc.
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DataSource(ABC):
    """
    Abstract interface for external document sources.

    Implementations:
    - InMemoryDataSource (sandbox testing)
    - GoogleSheetsDataSource (production)
    - NotionDataSource (future)
    - AirtableDataSource (future)
    """

    @abstractmethod
    def read(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Read data from the document.

        Parameters
        ----------
        query : dict, optional
            Query parameters:
            - limit: max rows to return
            - filter: dict of column conditions
            - sheet: sheet name (for multi-sheet documents)
            - offset: skip first N rows

        Returns
        -------
        List[Dict[str, Any]]
            Rows as list of dicts, where keys are column names
        """
        pass

    @abstractmethod
    def write(self, data: List[Dict[str, Any]], mode: str = "append") -> None:
        """
        Write data to the document.

        Parameters
        ----------
        data : List[Dict[str, Any]]
            Rows to write, where each dict has column names as keys
        mode : str
            Write mode:
            - "append": add rows to end
            - "replace": clear and write new data
            - "update": update matching rows (by first column as key)
        """
        pass

    @abstractmethod
    def get_schema(self) -> DocumentSchema:
        """
        Get the document schema.

        Returns
        -------
        DocumentSchema
            Schema describing document structure
        """
        pass

    @abstractmethod
    def query(self, conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Query the document with filter conditions.

        Parameters
        ----------
        conditions : Dict[str, Any]
            Column name -> expected value mapping
            Example: {"status": "pending", "votes": ">5"}

        Returns
        -------
        List[Dict[str, Any]]
            Matching rows
        """
        pass


class DataSourceRegistry:
    """
    Registry for managing data source instances.

    In sandbox: holds InMemoryDataSource instances for testing
    In production: holds real API connectors (GoogleSheetsDataSource, etc.)
    """

    def __init__(self):
        self._sources: Dict[str, DataSource] = {}
        self._factories: Dict[str, callable] = {}

    def register_factory(self, source_type: str, factory: callable) -> None:
        """
        Register a factory function for creating data sources.

        Parameters
        ----------
        source_type : str
            Type identifier (e.g., "google_sheets")
        factory : callable
            Function that takes a URL and returns a DataSource
        """
        self._factories[source_type] = factory

    def register_source(self, source_id: str, source: DataSource) -> None:
        """
        Register a specific data source instance.

        Parameters
        ----------
        source_id : str
            Unique identifier (typically the document URL)
        source : DataSource
            DataSource instance to register
        """
        self._sources[source_id] = source

    def get_source(self, source_url: str) -> DataSource:
        """
        Get or create a data source for the given URL.

        Parameters
        ----------
        source_url : str
            Document URL

        Returns
        -------
        DataSource
            DataSource instance for this URL

        Raises
        ------
        ValueError
            If no factory is registered for this source type
        """
        # Return existing source if already registered
        if source_url in self._sources:
            return self._sources[source_url]

        # Infer source type and create new source
        source_type = self._infer_source_type(source_url)
        if source_type not in self._factories:
            raise ValueError(f"No factory registered for source type: {source_type}")

        source = self._factories[source_type](source_url)
        self._sources[source_url] = source
        return source

    def _infer_source_type(self, url: str) -> str:
        """Infer source type from URL pattern."""
        if "docs.google.com/spreadsheets" in url:
            return "google_sheets"
        elif "notion.so" in url:
            return "notion"
        elif "airtable.com" in url:
            return "airtable"
        raise ValueError(f"Cannot infer source type from URL: {url}")

    def list_sources(self) -> List[str]:
        """Return list of registered source URLs."""
        return list(self._sources.keys())
