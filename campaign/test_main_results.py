"""Numerical contract tests for the publication's main result script."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.spatial.distance import jensenshannon
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import build_main_results as results


def test_jsd_is_divergence_in_bits_not_distance():
    assert results.js_divergence([1, 0], [0, 1]) == pytest.approx(1.)
    assert results.js_divergence([3, 2, 1], [3, 2, 1]) == pytest.approx(0.)
    p, q = [1, 2, 6], [4, 3, 2]
    assert results.js_divergence(p, q) == pytest.approx(jensenshannon(p, q, base=2)**2)
    assert results.js_divergence(p, q) == pytest.approx(results.js_divergence(q, p))
    with pytest.raises(ValueError):
        results.js_divergence([0, 0], [1, 0])


def test_weights_are_preserved_and_periodic_angles_wrap():
    spec = {"low": 0., "high": 2*np.pi, "periodic": True, "grid_bins": 512, "sigma_bins": 4.}
    x = np.array([.013, 1.234])
    weighted = results.marginal_mass(x, spec, [.25, .75])
    repeated = results.marginal_mass([x[0], x[1], x[1], x[1]], spec)
    wrapped = results.marginal_mass(x+2*np.pi, spec, [.25, .75])
    np.testing.assert_allclose(weighted, repeated, atol=1e-15)
    np.testing.assert_allclose(weighted, wrapped, atol=1e-15)
    assert weighted.sum() == pytest.approx(1.)


def test_estimator_agrees_with_independent_gaussian_integral():
    x = norm.ppf((np.arange(4096)+.5)/4096)
    spec = results.marginal_spec(x, -6., 6.)
    estimated = results.js_divergence(results.marginal_mass(x, spec), results.marginal_mass(x+.5, spec))
    sigma = np.sqrt(1+spec["bandwidth"]**2)

    def integrand(t):
        p, q = norm.pdf(t, scale=sigma), norm.pdf(t, loc=.5, scale=sigma)
        m = (p+q)/2
        return .5*(p*np.log2(p/m)+q*np.log2(q/m))

    independent = quad(integrand, -10, 10, epsabs=1e-10)[0]
    assert estimated == pytest.approx(independent, abs=2e-4)


def test_reference_shape_sets_grid_and_all_samples_stay_on_support():
    reference = np.linspace(.01, .99, 1000)
    spec = results.marginal_spec(reference, 0., 1.)
    assert 512 <= spec["grid_bins"] <= 8192
    assert results.marginal_mass(reference, spec).sum() == pytest.approx(1.)
    with pytest.raises(ValueError, match="outside prior"):
        results.marginal_mass([-.1, .5], spec)


def test_cached_nis_weights_and_evidence_are_checked(tmp_path):
    path = tmp_path / "result.npz"
    metadata = {"parameter_names": list(results.PARAMETERS), "logz": -3.}
    np.savez(path, metadata_json=np.array(json.dumps(metadata)), dead_theta=np.zeros((1, 8)),
             final_live_theta=np.ones((1, 8)), log_posterior_weights=np.log([.25, .75]))
    samples, weights = results.load_nis(path, {"nis": {"log_evidence": -3.}}, results.digest(path))
    np.testing.assert_array_equal(samples[:, 0], [0, 1])
    np.testing.assert_allclose(weights, [.25, .75])
    with pytest.raises(ValueError, match="evidence disagrees"):
        results.load_nis(path, {"nis": {"log_evidence": -2.}}, results.digest(path))
    np.savez(path, metadata_json=np.array(json.dumps(metadata)), dead_theta=np.zeros((1, 8)),
             final_live_theta=np.ones((1, 8)), log_posterior_weights=np.log([.250001, .75]))
    with pytest.raises(ValueError, match="Invalid cached NIS posterior"):
        results.load_nis(path, {"nis": {"log_evidence": -3.}}, results.digest(path))
