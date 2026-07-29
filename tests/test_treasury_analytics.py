"""Tests for the treasury analytics layer."""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from treasury import config as cfg


def test_config_exposes_calibration_constants():
    assert cfg.SEED == 20260729
    assert cfg.TRADING_DAYS_PER_YEAR == 252
    assert pd.Timestamp(cfg.START) < pd.Timestamp(cfg.REGIME_SPLIT) < pd.Timestamp(cfg.END)
    # Two regimes: the defensive first period and the drifted second period.
    assert set(cfg.REGIMES) == {"FY2025", "FY2026"}
    for name, r in cfg.REGIMES.items():
        assert set(r) == {"mkt", "smb", "hml", "rmw", "cma", "idio", "alpha"}
    # The planted drift: market beta rises through the policy limit.
    assert cfg.REGIMES["FY2025"]["mkt"] < cfg.POLICY["max_beta"] < cfg.REGIMES["FY2026"]["mkt"]


def test_config_policy_limits_are_the_spec_values():
    assert cfg.POLICY["max_beta"] == 1.00
    assert cfg.POLICY["max_drawdown"] == 0.10
    assert cfg.POLICY["min_net_alpha"] == 0.0


def test_data_dir_is_not_gitignored():
    # data/ and docs/ are excluded by .gitignore; treasury data must not land there.
    parts = cfg.DATA_DIR.parts
    assert "data_compact" in parts
    assert "docs" not in parts
