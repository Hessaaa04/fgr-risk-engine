"""Synthetic portfolio data with the shape of the real portfolio and none of its contents.

Every name, number and flow here is generated from a fixed random seed. Nothing is
derived from real holdings. Use this for development, tests and demonstrations.
"""

from .generator import SyntheticPortfolio, generate

__all__ = ["SyntheticPortfolio", "generate"]
