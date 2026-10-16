"""
Setup script for PolicyKit Sandbox.

Install in development mode:
    pip install -e .

This makes sandboxengine importable without sys.path manipulation.
"""

from setuptools import setup, find_packages

setup(
    name="policykit-sandbox",
    version="1.0.0",
    description="PolicyKit governance script testing sandbox",
    author="PolicyKit Team",
    packages=find_packages(where="sandboxengine"),
    package_dir={"": "sandboxengine"},
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.0.0",
        "slowapi>=0.1.9",
        "boto3>=1.34.0",  # Only for credentials endpoint
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "httpx>=0.25.0",  # For testing FastAPI
        ]
    },
    entry_points={
        "console_scripts": [
            "sandbox-server=sandboxengine.main:main",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
