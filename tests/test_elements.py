from PySide6.QtCore import QCoreApplication, QEvent

from utils.ui.elements import TabBar


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
