from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="bus-arrival-board",
    version="0.1.0",
    author="Garfield Wu",
    author_email="wu_garfield@163.com",
    description="Real-time bus arrival information display system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Garfield-Wuu/BusArrivalBoard",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=[
        "requests>=2.31.0",
        "brotli>=1.0.9",
        "cryptography>=41.0.0",
        "PyYAML>=6.0.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "bus-arrival=bus_arrival_board.cli:main",
        ],
    },
)
