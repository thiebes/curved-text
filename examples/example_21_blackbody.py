"""Blackbody spectra, labelled along their paths.

Planck's law gives the spectral radiance of a blackbody at temperature T:
B(λ, T) = 2hc² / λ⁵ / (exp(hc / λkT) - 1). Four temperatures from a cool
star to the Sun's effective temperature, 5772 K, on a logarithmic radiance
axis, where the curves stack in order of temperature. Each label rides its
own curve just past its peak, which Wien's law puts at 2898 μm K / T, so no
legend is needed.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import REFERENCE_COLOR, TEXT, data_axes, figure, save

# The SI defining constants: Planck, the speed of light, and Boltzmann; and
# Wien's displacement constant, which puts the peak at WIEN_UM_K / T.
H = 6.62607015e-34
C = 299792458.0
K_B = 1.380649e-23
WIEN_UM_K = 2897.771955

# Temperature (K), colour of the line and its label, label, and offset
# (points). The Sun is the reference curve, so it is drawn in near-black, and
# its label sits
# above it, in the open space; the others sit below their curves, where the
# gap to the next curve is widest.
SERIES = [
    (5772, REFERENCE_COLOR, "5772 K, the Sun", 8.0),
    (5000, TEXT["blue"], "5000 K", -8.0),
    (4000, TEXT["green"], "4000 K", -8.0),
    (3000, TEXT["gold"], "3000 K", -8.0),
]
# Each label rides the stretch of its curve just past the peak, from 0.9 to
# 1.8 times the peak wavelength, centred.
LABEL_SPAN_OVER_PEAK = (0.9, 1.8)
WAVELENGTH_UM = (0.1, 3.0)
# The radiance axis: the top leaves room for the Sun's label above its peak,
# and the bottom cuts off the steep short-wavelength flanks, which fall many
# decades lower.
RADIANCE_LIMITS = (1e4, 6e7)


def spectral_radiance(wavelength_um, temperature):
    """Planck's law, in W sr⁻¹ m⁻² μm⁻¹."""
    wavelength = wavelength_um * 1e-6
    per_metre = (2 * H * C ** 2 / wavelength ** 5
                 / np.expm1(H * C / (wavelength * K_B * temperature)))
    return per_metre * 1e-6


def make(images_dir):
    fig = figure(17, 9, font_size=9)
    ax = data_axes(fig.subplots())

    wavelength = np.linspace(*WAVELENGTH_UM, 1000)
    for temperature, color, label, offset in SERIES:
        radiance = spectral_radiance(wavelength, temperature)
        ax.plot(wavelength, radiance, color=color, linewidth=2)
        peak = WIEN_UM_K / temperature
        span = ((wavelength >= LABEL_SPAN_OVER_PEAK[0] * peak)
                & (wavelength <= LABEL_SPAN_OVER_PEAK[1] * peak))
        curved_text(ax, wavelength[span], radiance[span], label, pos=0.5,
                    anchor="center", offset=offset, color=color, fontsize=9)
    ax.set_yscale("log")
    ax.set_xlim(*WAVELENGTH_UM)
    ax.set_ylim(*RADIANCE_LIMITS)
    ax.set_xlabel("wavelength (μm)")
    ax.set_ylabel("spectral radiance (W sr⁻¹ m⁻² μm⁻¹)")

    path = os.path.join(images_dir, "21_blackbody.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
