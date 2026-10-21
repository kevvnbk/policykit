"""
Tests for external document data sources.
"""

import pytest
from sandboxengine.policyengine.datasources import (
    DocumentSchema,
    DataSource,
    DataSourceRegistry,
)
from sandboxengine.policyengine.datasources import InMemoryDataSource


def test_document_schema_creation():
    """Test creating a DocumentSchema."""
    schema = DocumentSchema(
        source_type="google_sheets",
        source_url="https://docs.google.com/spreadsheets/d/test123",
        structure={
            "columns": ["name", "email", "role"],
            "sheet_names": ["Members"]
        },
        sample_data=[
            {"name": "Alice", "email": "alice@example.com", "role": "admin"}
        ],
        metadata={"row_count": 10, "col_count": 3}
    )

    assert schema.source_type == "google_sheets"
    assert schema.source_url == "https://docs.google.com/spreadsheets/d/test123"
    assert len(schema.structure["columns"]) == 3
    assert len(schema.sample_data) == 1


def test_in_memory_data_source_read():
    """Test reading from in-memory data source."""
    schema = DocumentSchema(
        source_type="test",
        source_url="test://example",
        structure={"columns": ["name", "age"]},
        sample_data=[],
        metadata={}
    )

    source = InMemoryDataSource(schema, [
        {"name": "Alice", "age": "30"},
        {"name": "Bob", "age": "25"},
        {"name": "Charlie", "age": "35"}
    ])

    # Read all data
    data = source.read()
    assert len(data) == 3
    assert data[0]["name"] == "Alice"

    # Read with limit
    limited = source.read({"limit": 2})
    assert len(limited) == 2

    # Read with offset
    offset = source.read({"offset": 1})
    assert len(offset) == 2
    assert offset[0]["name"] == "Bob"


def test_in_memory_data_source_query():
    """Test querying in-memory data source."""
    schema = DocumentSchema(
        source_type="test",
        source_url="test://example",
        structure={"columns": ["name", "age", "status"]},
        sample_data=[],
        metadata={}
    )

    source = InMemoryDataSource(schema, [
        {"name": "Alice", "age": "30", "status": "active"},
        {"name": "Bob", "age": "25", "status": "inactive"},
        {"name": "Charlie", "age": "35", "status": "active"}
    ])

    # Query exact match
    results = source.query({"status": "active"})
    assert len(results) == 2
    assert all(r["status"] == "active" for r in results)

    # Query with comparison (greater than)
    results = source.query({"age": ">28"})
    assert len(results) == 2  # Alice (30) and Charlie (35)

    # Query with comparison (less than)
    results = source.query({"age": "<30"})
    assert len(results) == 1  # Bob (25)


def test_in_memory_data_source_write_append():
    """Test appending to in-memory data source."""
    schema = DocumentSchema(
        source_type="test",
        source_url="test://example",
        structure={"columns": ["name", "email"]},
        sample_data=[],
        metadata={}
    )

    source = InMemoryDataSource(schema, [
        {"name": "Alice", "email": "alice@example.com"}
    ])

    # Append data
    source.write([
        {"name": "Bob", "email": "bob@example.com"}
    ], mode="append")

    assert source.get_row_count() == 2
    assert source.get_write_count() == 1

    data = source.read()
    assert data[1]["name"] == "Bob"


def test_in_memory_data_source_write_replace():
    """Test replacing data in in-memory data source."""
    schema = DocumentSchema(
        source_type="test",
        source_url="test://example",
        structure={"columns": ["name"]},
        sample_data=[],
        metadata={}
    )

    source = InMemoryDataSource(schema, [
        {"name": "Alice"},
        {"name": "Bob"}
    ])

    # Replace all data
    source.write([
        {"name": "Charlie"}
    ], mode="replace")

    assert source.get_row_count() == 1
    assert source.get_write_count() == 1

    data = source.read()
    assert data[0]["name"] == "Charlie"


def test_in_memory_data_source_write_update():
    """Test updating data in in-memory data source."""
    schema = DocumentSchema(
        source_type="test",
        source_url="test://example",
        structure={"columns": ["id", "name", "status"]},
        sample_data=[],
        metadata={}
    )

    source = InMemoryDataSource(schema, [
        {"id": "1", "name": "Alice", "status": "active"},
        {"id": "2", "name": "Bob", "status": "inactive"}
    ])

    # Update existing row (matches on first column: id)
    source.write([
        {"id": "1", "name": "Alice", "status": "inactive"}
    ], mode="update")

    data = source.read()
    assert data[0]["status"] == "inactive"
    assert source.get_row_count() == 2  # Still 2 rows


def test_data_source_registry():
    """Test DataSourceRegistry."""
    registry = DataSourceRegistry()

    # Register a factory
    def create_test_source(url):
        schema = DocumentSchema(
            source_type="test",
            source_url=url,
            structure={},
            sample_data=[],
            metadata={}
        )
        return InMemoryDataSource(schema, [])

    registry.register_factory("test", create_test_source)

    # Factory not called until get_source
    assert len(registry.list_sources()) == 0

    # Now would create source if we had proper URL inference
    # But we can directly register a source
    test_url = "test://example"
    test_source = create_test_source(test_url)
    registry.register_source(test_url, test_source)

    assert len(registry.list_sources()) == 1
    assert test_url in registry.list_sources()

    # Get the same source back
    retrieved = registry.get_source(test_url)
    assert retrieved is test_source


def test_data_source_registry_infer_google_sheets():
    """Test inferring Google Sheets source type."""
    registry = DataSourceRegistry()

    # Should infer google_sheets
    url = "https://docs.google.com/spreadsheets/d/abc123/edit"
    assert registry._infer_source_type(url) == "google_sheets"


def test_data_source_registry_unknown_type():
    """Test error on unknown source type."""
    registry = DataSourceRegistry()

    with pytest.raises(ValueError, match="Cannot infer source type"):
        registry._infer_source_type("https://unknown.com/document")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
