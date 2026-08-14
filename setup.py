from setuptools import setup, find_packages

setup(
    name="agentos-runtime",
    version="0.2.0",
    description="Portable AgentOS Runtime Core and Distributed Node Client",
    author="AgentOS Core Team",
    packages=find_packages(include=["runtime_core*", "agentos_node*"]),
    entry_points={
        "console_scripts": [
            "agentos-node=agentos_node.cli:main",
        ],
    },
    install_requires=[
        "pyyaml>=6.0",
    ],
    python_requires=">=3.9",
)
