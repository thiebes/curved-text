"""Shared test setup: force a headless backend before pyplot is imported."""
import matplotlib

matplotlib.use("Agg")
