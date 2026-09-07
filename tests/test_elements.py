from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QColor

from utils.ui.elements import TabBar, IconButton, Icons


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
