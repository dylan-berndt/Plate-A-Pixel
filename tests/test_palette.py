import pytest

from utils.data.palette import Palette, PaletteEntry


@pytest.fixture
def palette():
    return Palette([(30, 30, 200), (200, 30, 30), (40, 180, 90)])


def test_palette_length_and_colors_match_input_order(palette):
    assert len(palette) == 3
    assert tuple(palette.colors[1]) == (200, 30, 30)


def test_entries_default_to_unnamed(palette):
    for entry in palette:
        assert entry.name == ""


def test_index_of_finds_a_matching_color(palette):
    assert palette.indexOf((200, 30, 30)) == 1


def test_index_of_returns_none_for_an_unknown_color(palette):
    assert palette.indexOf((1, 2, 3)) is None


def test_rename_mutates_the_entry_in_place(palette):
    palette.rename(0, "Blue")

    assert palette[0].name == "Blue"


def test_set_color_updates_the_entry_and_the_colors_array(palette):
    palette.setColor(2, (10, 20, 30))

    assert palette[2].color == (10, 20, 30)
    assert tuple(palette.colors[2]) == (10, 20, 30)


def test_to_dict_from_dict_round_trip_preserves_name(palette):
    palette.rename(1, "Red")

    restored = Palette.from_dict(palette.to_dict())

    assert len(restored) == 3
    assert restored[1].name == "Red"
    assert restored[1].color == (200, 30, 30)
    assert restored[0].name == ""


def test_palette_entry_to_dict_has_plain_int_color_components():
    entry = PaletteEntry(color=(30, 30, 200), name="Blue")

    d = entry.to_dict()

    assert d == {"color": [30, 30, 200], "name": "Blue"}
