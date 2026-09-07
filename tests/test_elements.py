from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QColor

from utils.ui.elements import (
    TabBar, IconButton, Icons, PillToggle, NineSliceButton, NineSliceLineEdit, Dropdown, ViewModeTabs,
)


def test_tab_bar_survives_repeated_set_tabs_with_deferred_deletion_flushed():
    # Regression: setTabs() used to deleteLater() every widget currently
    # in its layout to clear it for a rebuild, including _newTabButton -
    # a single persistent widget re-added at the end of *every* call
    # rather than recreated. That queues its actual C++ object for
    # destruction on the next event-loop pass; once that fires, the next
    # setTabs() call reuses (and tries to deleteLater() or addWidget())
    # a Python wrapper around an already-deleted object, raising
    # "Internal C++ object (IconButton) already deleted" - exactly what
    # happened switching project tabs in a real running app, where the
    # event loop gets to actually process events between calls.
    bar = TabBar(onSelect=lambda i: None, onClose=lambda i: None, onNewTab=lambda: None)

    for i in range(5):
        bar.setTabs([("Project A", i % 2 == 0, False), ("Project B", i % 2 == 1, True)])
        # Forces the deferred deletion right away instead of leaving it
        # to whenever the ambient event loop happens to get to it -
        # deterministic, rather than relying on processEvents() timing.
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)  # should not raise

    assert bar._layout.count() == 3  # 2 tabs + the persistent new-tab button


# -- IconButton --------------------------------------------------------------

def test_icon_button_defaults_to_bordered_with_a_shared_nine_slice():
    button = IconButton(Icons.WAND)
    assert button._bordered is True
    assert button._nineSlice is not None


def test_icon_button_bordered_false_skips_nine_slice_state():
    button = IconButton(Icons.PENCIL, size=16, bordered=False)
    assert button._bordered is False
    assert not hasattr(button, "_nineSlice")


def test_icon_button_paint_event_does_not_raise_for_either_mode():
    bordered = IconButton(Icons.WAND)
    bordered.resize(40, 40)
    ghost = IconButton(Icons.PENCIL, size=16, bordered=False)
    ghost.resize(16, 16)
    bordered.repaint()  # should not raise
    ghost.repaint()  # should not raise


def test_icon_button_checked_state_selects_the_active_color():
    button = IconButton(Icons.WAND, checkable=True, activeColor="#123456")
    button.setChecked(True)
    assert button._activeColor == QColor("#123456")


# -- other nine-slice-bordered buttons ---------------------------------------

def test_pill_toggle_fill_color_follows_checked_state():
    toggle = PillToggle("Contiguous")
    toggle.resize(80, 24)
    assert toggle._fillColor() == toggle._offColor
    toggle.setChecked(True)
    assert toggle._fillColor() == toggle._onColor
    toggle.repaint()  # should not raise


def test_nine_slice_button_paints_without_raising_and_fires_on_click():
    calls = []
    button = NineSliceButton("Reset", onClick=lambda: calls.append(True))
    button.resize(80, 24)
    button.repaint()  # should not raise
    button.click()
    assert calls == [True]


def test_nine_slice_line_edit_reserves_border_thickness_as_text_margins():
    edit = NineSliceLineEdit("hello")
    edit.resize(120, 24)
    t = edit._nineSlice.borderThickness(2)  # STANDARD_SCALE
    assert edit.textMargins().left() == t + 2
    assert edit.text() == "hello"
    edit.repaint()  # should not raise


def test_dropdown_paints_without_raising():
    dropdown = Dropdown({"One": 1, "Two": 2})
    dropdown.resize(120, 24)
    dropdown.repaint()  # should not raise
    assert dropdown.currentData() == 1


def test_view_mode_tabs_active_button_tracks_setActive():
    tabs = ViewModeTabs(modes=("Canvas", "Layer", "Mesh"), active="Canvas")
    assert tabs._buttons["Canvas"]._active is True
    assert tabs._buttons["Layer"]._active is False

    tabs.setActive("Layer")

    assert tabs._buttons["Canvas"]._active is False
    assert tabs._buttons["Layer"]._active is True
