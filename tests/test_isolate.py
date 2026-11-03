import os
import time

import pytest

from fleetattention.cli import SWEEP, run_seeds
from fleetattention.isolate import Isolated, SupervisorError
from fleetattention.supervisors import by_name
from fleetattention.world import Config, DecisionError, Episode

from hostile import MARKER

SHORT = Config(hours=.1)


def test_an_isolated_supervisor_scores_the_same():
    with Isolated('cost_aware') as isolated:
        assert Episode(isolated, 3, SHORT).run() == Episode(by_name('cost_aware'), 3, SHORT).run()
    with Isolated('reference') as isolated:
        row = Episode(isolated, 3, SHORT).run()
        assert row == Episode(by_name('reference'), 3, SHORT).run()
        asked = {k: v for k, v in isolated.report().items() if 'busy_default' not in k and k != 'reason_joined'}
        assert sum(asked.values()) == row['questions'] > 0


def test_an_isolated_supervisor_cannot_reach_the_simulator():
    in_process = Episode(by_name('peek:Peek'), 1, SHORT).run()
    assert in_process['questions'] == 0  # it read every answer from the simulator
    with Isolated('peek:Peek') as isolated:
        isolated_row = Episode(isolated, 1, SHORT).run()
    assert isolated_row['questions'] == isolated_row['incidents'] > 0


def test_the_key_stays_out_of_the_supervisors_process():
    row, = run_seeds('hostile:Snoop', 1, Config(hours=.01), key=MARKER, isolate=True)
    assert row['reported_key_seen'] == 0 and row['reported_files_here'] == 0 and row['reported_env'] <= 2


def test_public_seeds_can_be_recognised_but_secret_ones_cannot():
    public, = run_seeds('hostile:Shadow', 1, Config(hours=.01), isolate=True)
    secret, = run_seeds('hostile:Shadow', 1, Config(hours=.01), key=MARKER, isolate=True)
    assert public['reported_found'] == 1 and secret['reported_found'] == 0


@pytest.mark.parametrize('spec, problem', [('hostile:Sleepy', 'did not reply'), ('hostile:Loud', 'longer than'),
                                           ('hostile:Crash', 'exited')])
def test_a_broken_supervisor_fails_fast_and_is_killed(spec, problem):
    start = time.monotonic()
    isolated = Isolated(spec, timeout=.5)
    with pytest.raises(SupervisorError, match=problem):
        Episode(isolated, 0, SHORT).run()
    assert time.monotonic() - start < 10 and isolated.process.poll() is not None


@pytest.mark.parametrize('spec, problem', [('hostile:Flood', 'out of turn|more than one'),
                                           ('hostile:Infinite', 'not JSON'), ('hostile:Huge', 'report'),
                                           ('hostile:BadKey', 'report')])
def test_a_supervisor_that_breaks_the_protocol_is_stopped_quickly(spec, problem):
    start = time.monotonic()
    with pytest.raises(SupervisorError, match=problem):
        run_seeds(spec, 1, Config(hours=.2), isolate=True)
    assert time.monotonic() - start < 15


def test_an_illegal_action_from_an_isolated_supervisor_is_refused():
    with pytest.raises(DecisionError, match='teleport'):
        run_seeds('hostile:Teleport', 1, SHORT, isolate=True)


def test_processes_and_files_of_an_episode_do_not_outlive_it():
    isolated = Isolated('hostile:Spawner')
    Episode(isolated, 0, Config(hours=.01)).run()
    report = isolated.report()
    workdir = isolated.workdir
    isolated.close()
    assert report['cwd_is_temp'] == 1 and not os.path.exists(workdir)
    time.sleep(.2)
    with pytest.raises(ProcessLookupError):
        os.kill(int(report['pid']), 0)


def test_the_results_name_the_spec_not_what_the_supervisor_calls_itself():
    row, = run_seeds('hostile:Snoop', 1, Config(hours=.01), isolate=True)
    assert row['supervisor'] == 'hostile:Snoop'


@pytest.mark.parametrize('name', SWEEP)
def test_every_baseline_scores_the_same_isolated(name):
    config = Config(hours=.05)
    with Isolated(name) as isolated:
        assert Episode(isolated, 2, config).run() == Episode(by_name(name), 2, config).run()


def test_the_reference_supervisors_report_is_accepted_by_isolation():
    from fleetattention.isolate import REPORT_KEY
    for key in ('reason_shadow', 'reason_busy_default:audit', 'reason_busy_default:below_threshold'):
        assert REPORT_KEY.fullmatch(key)
