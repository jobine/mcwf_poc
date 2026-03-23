#!/usr/bin/env python3
"""setup.py for cli-anything-ansa

Install with: pip install -e .
"""

from setuptools import setup, find_namespace_packages

with open("cli_anything/ansa/README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="cli-anything-ansa",
    version="1.0.0",
    author="cli-anything contributors",
    description=(
        "CLI harness for BETA CAE Systems ANSA pre-processor — "
        "batch meshing, quality checks, and solver output via IAP protocol. "
        "Requires: ANSA v22+ (set ANSA_HOME environment variable)"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/HKUDS/CLI-Anything",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Physics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-ansa=cli_anything.ansa.ansa_cli:cli",
        ],
    },
    package_data={
        "cli_anything.ansa": ["skills/*.md"],
    },
    include_package_data=True,
    zip_safe=False,
)
