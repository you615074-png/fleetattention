from fleetattention.layout import warehouse


def test_every_free_cell_is_reachable_from_every_station():
    layout = warehouse()
    free = [(x, y) for x in range(layout.width) for y in range(layout.height) if layout.free((x, y))]
    start = layout.stations[0]
    for cell in free:
        assert layout.path(start, cell) is not None, cell


def test_stations_and_chargers_are_bays_off_the_edge_columns():
    layout = warehouse()
    for bay in layout.stations + layout.chargers:
        assert layout.free(bay)
        assert len(list(layout.neighbors(bay))) == 1, bay


def test_picks_face_racks_and_are_not_bays():
    layout = warehouse()
    assert layout.picks
    for pick in layout.picks:
        assert layout.free(pick) and pick not in layout.stations and pick not in layout.chargers
