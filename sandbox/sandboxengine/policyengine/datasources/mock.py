"""
In-memory mock implementations of DataSource for sandbox testing.

PolicyKit equivalent: None (sandbox-specific)
"""

from typing import Any, Dict, List, Optional
from .base import DataSource, DocumentSchema


class InMemoryDataSource(DataSource):
    """
    In-memory document source for sandbox testing.

    Simulates external document operations without API calls.
    Tracks all writes for assertion validation.
    """

    def __init__(self, schema: DocumentSchema, initial_data: Optional[List[Dict]] = None):
        """
        Initialize in-memory data source.

        Parameters
        ----------
        schema : DocumentSchema
            Document schema (structure, columns, metadata)
        initial_data : List[Dict], optional
            Initial data to populate the document with
        """
        self.schema = schema
        self.data = initial_data.copy() if initial_data else []
        self.write_log: List[Dict[str, Any]] = []  # Track all writes for assertions

    def read(self, query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Read data from in-memory storage.

        Supports filtering and limiting via query parameters.
        """
        if query is None:
            return self.data.copy()

        results = self.data.copy()

        # Apply filter
        if "filter" in query:
            results = [
                row for row in results
                if self._matches_filter(row, query["filter"])
            ]

        # Apply limit
        if "limit" in query:
            results = results[:query["limit"]]

        # Apply offset
        if "offset" in query:
            results = results[query["offset"]:]

        return results

    def write(self, data: List[Dict[str, Any]], mode: str = "append") -> None:
        """
        Write data to in-memory storage.

        Logs the write operation for test assertions.
        """
        # Log the write
        self.write_log.append({
            "data": data.copy(),
            "mode": mode,
            "row_count": len(data)
        })

        if mode == "append":
            self.data.extend(data)

        elif mode == "replace":
            self.data = data.copy()

        elif mode == "update":
            # Update by matching first column (assumed to be ID/key)
            if not data or not self.data:
                return

            key_column = list(data[0].keys())[0] if data[0] else None
            if not key_column:
                return

            for new_row in data:
                key_value = new_row.get(key_column)
                updated = False

                for i, existing_row in enumerate(self.data):
                    if existing_row.get(key_column) == key_value:
                        self.data[i] = new_row
                        updated = True
                        break

                # If no match found, append
                if not updated:
                    self.data.append(new_row)

        else:
            raise ValueError(f"Unknown write mode: {mode}")

    def get_schema(self) -> DocumentSchema:
        """Return the document schema."""
        return self.schema

    def query(self, conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Query with filter conditions.

        Supports exact matching and simple comparison operators.
        """
        return [
            row for row in self.data
            if self._matches_filter(row, conditions)
        ]

    def _matches_filter(self, row: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        """
        Check if a row matches filter conditions.

        Supports:
        - Exact match: {"status": "pending"}
        - Greater than: {"votes": ">5"}
        - Less than: {"votes": "<10"}
        - Not equal: {"status": "!approved"}
        """
        for key, expected_value in filter_dict.items():
            if key not in row:
                return False

            actual_value = row[key]

            # Handle comparison operators (as strings)
            if isinstance(expected_value, str):
                if expected_value.startswith(">"):
                    try:
                        threshold = float(expected_value[1:])
                        if not (float(actual_value) > threshold):
                            return False
                    except (ValueError, TypeError):
                        return False

                elif expected_value.startswith("<"):
                    try:
                        threshold = float(expected_value[1:])
                        if not (float(actual_value) < threshold):
                            return False
                    except (ValueError, TypeError):
                        return False

                elif expected_value.startswith("!"):
                    # Not equal
                    if actual_value == expected_value[1:]:
                        return False

                else:
                    # Exact match
                    if actual_value != expected_value:
                        return False
            else:
                # Non-string: direct comparison
                if actual_value != expected_value:
                    return False

        return True

    def clear(self) -> None:
        """Clear all data (useful for test cleanup)."""
        self.data = []
        self.write_log = []

    def get_write_count(self) -> int:
        """Return number of write operations performed."""
        return len(self.write_log)

    def get_row_count(self) -> int:
        """Return current number of rows."""
        return len(self.data)
