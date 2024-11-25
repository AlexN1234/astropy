# Licensed under a 3-clause BSD style license - see LICENSE.rst

import warnings
from unittest.mock import patch

import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
import pytest

from astropy import units as u
from astropy.io import fits
from astropy.utils.data import get_pkg_data_filename
from astropy.utils.exceptions import AstropyDeprecationWarning
from astropy.visualization.wcsaxes.coordinate_helpers import CoordinateHelper
from astropy.visualization.wcsaxes.core import WCSAxes
from astropy.wcs import WCS

MSX_HEADER = fits.Header.fromtextfile(get_pkg_data_filename("data/msx_header"))


def teardown_function(function):
    plt.close("all")


def test_getaxislabel(ignore_matplotlibrc):
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], aspect="equal")

    ax.coords[0].set_axislabel("X")
    ax.coords[1].set_axislabel("Y")
    assert ax.coords[0].get_axislabel() == "X"
    assert ax.coords[1].get_axislabel() == "Y"


@pytest.fixture
def ax():
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], aspect="equal")
    fig.add_axes(ax)

    return ax


def assert_label_draw(ax, x_label, y_label):
    ax.coords[0].set_axislabel("Label 1")
    ax.coords[1].set_axislabel("Label 2")

    with patch.object(ax.coords[0]._axislabels, "set_position") as pos1:
        with patch.object(ax.coords[1]._axislabels, "set_position") as pos2:
            ax.figure.canvas.draw()

    assert pos1.call_count == x_label
    assert pos2.call_count == y_label


def test_label_visibility_rules_default(ignore_matplotlibrc, ax):
    assert_label_draw(ax, True, True)


def test_label_visibility_rules_label(ignore_matplotlibrc, ax):
    ax.coords[0].set_ticklabel_visible(False)
    ax.coords[1].set_ticks(values=[-9999] * u.one)

    assert_label_draw(ax, False, False)


def test_label_visibility_rules_ticks(ignore_matplotlibrc, ax):
    ax.coords[0].set_axislabel_visibility_rule("ticks")
    ax.coords[1].set_axislabel_visibility_rule("ticks")

    ax.coords[0].set_ticklabel_visible(False)
    ax.coords[1].set_ticks(values=[-9999] * u.one)

    assert_label_draw(ax, True, False)


def test_label_visibility_rules_always(ignore_matplotlibrc, ax):
    ax.coords[0].set_axislabel_visibility_rule("always")
    ax.coords[1].set_axislabel_visibility_rule("always")

    ax.coords[0].set_ticklabel_visible(False)
    ax.coords[1].set_ticks(values=[-9999] * u.one)

    assert_label_draw(ax, True, True)


def test_format_unit():
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], wcs=WCS(MSX_HEADER))
    fig.add_axes(ax)

    # Force a draw which is required for format_coord to work
    ax.figure.canvas.draw()

    ori_fu = ax.coords[1].get_format_unit()
    assert ori_fu == "deg"

    ax.coords[1].set_format_unit("arcsec")
    fu = ax.coords[1].get_format_unit()
    assert fu == "arcsec"


def test_set_separator():
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], wcs=WCS(MSX_HEADER))
    fig.add_axes(ax)

    # Force a draw which is required for format_coord to work
    ax.figure.canvas.draw()

    ax.coords[1].set_format_unit("deg")
    assert ax.coords[1].format_coord(4) == "4\xb000'00\""
    ax.coords[1].set_separator((":", ":", ""))
    assert ax.coords[1].format_coord(4) == "4:00:00"
    ax.coords[1].set_separator("abc")
    assert ax.coords[1].format_coord(4) == "4a00b00c"
    ax.coords[1].set_separator(None)
    assert ax.coords[1].format_coord(4) == "4\xb000'00\""


@pytest.mark.parametrize(
    "draw_grid, expected_visibility", [(True, True), (False, False), (None, True)]
)
def test_grid_variations(ignore_matplotlibrc, draw_grid, expected_visibility):
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], aspect="equal")
    fig.add_axes(ax)
    transform = transforms.Affine2D().scale(2.0)
    coord_helper = CoordinateHelper(parent_axes=ax, transform=transform)
    coord_helper.grid(draw_grid=draw_grid)
    assert coord_helper._grid_lines_kwargs["visible"] == expected_visibility


def test_get_position():
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], aspect="equal")
    fig.add_axes(ax)

    assert ax.coords[0].get_ticks_position() == ["b", "r", "t", "l"]
    assert ax.coords[1].get_ticks_position() == ["b", "r", "t", "l"]
    assert ax.coords[0].get_ticklabel_position() == ["#"]
    assert ax.coords[1].get_ticklabel_position() == ["#"]
    assert ax.coords[0].get_axislabel_position() == ["#"]
    assert ax.coords[1].get_axislabel_position() == ["#"]

    fig.canvas.draw()

    assert ax.coords[0].get_ticks_position() == ["b", "r", "t", "l"]
    assert ax.coords[1].get_ticks_position() == ["b", "r", "t", "l"]
    assert ax.coords[0].get_ticklabel_position() == ["b", "#"]
    assert ax.coords[1].get_ticklabel_position() == ["l", "#"]
    assert ax.coords[0].get_axislabel_position() == ["b", "#"]
    assert ax.coords[1].get_axislabel_position() == ["l", "#"]

    ax.coords[0].set_ticks_position("br")
    ax.coords[1].set_ticks_position("tl")
    ax.coords[0].set_ticklabel_position("bt")
    ax.coords[1].set_ticklabel_position("rl")
    ax.coords[0].set_axislabel_position("t")
    ax.coords[1].set_axislabel_position("r")

    assert ax.coords[0].get_ticks_position() == ["b", "r"]
    assert ax.coords[1].get_ticks_position() == ["t", "l"]
    assert ax.coords[0].get_ticklabel_position() == ["b", "t"]
    assert ax.coords[1].get_ticklabel_position() == ["r", "l"]
    assert ax.coords[0].get_axislabel_position() == ["t"]
    assert ax.coords[1].get_axislabel_position() == ["r"]


def test_getters():
    fig = plt.figure()
    ax = WCSAxes(fig, [0.1, 0.1, 0.8, 0.8], aspect="equal")
    helper = CoordinateHelper(parent_axes=ax)

    assert helper.parent_axes == helper._parent_axes
    assert helper.parent_map == helper._parent_map
    assert helper.transform == helper._transform
    assert helper.coord_index == helper._coord_index
    assert helper.coord_type == helper._coord_type
    assert helper.coord_unit == helper._coord_unit
    assert helper.coord_wrap == helper._coord_wrap
    assert helper.frame == helper._frame
    assert helper.default_label == helper._default_label

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=AstropyDeprecationWarning)
        assert helper.ticks == helper._ticks
        assert helper.ticklabels == helper._ticklabels
        assert helper.axislabels == helper._axislabels
