import csv

import pytest

from fleetattention.cli import episode_seed, main


def test_run_writes_episode_and_summary_csv(tmp_path, capsys):
    main(['run', 'cost_aware', '--seeds', '2', '--hours', '.02', '--out', str(tmp_path), '--events', str(tmp_path / 'e.jsonl')])
    assert 'cost_aware' in capsys.readouterr().out
    with (tmp_path / 'run-episodes.csv').open() as f:
        assert [row['seed'] for row in csv.DictReader(f)] == ['0', '1']
    assert (tmp_path / 'run-summary.csv').exists() and (tmp_path / 'e.jsonl').exists()


def test_a_seed_key_replaces_the_public_seeds_and_stays_out_of_the_results(tmp_path, capsys):
    assert episode_seed(3, None) == 3 and 'secret' not in episode_seed(3, 'secret')
    assert episode_seed(3, 'secret') != episode_seed(3, 'other')
    key_file = tmp_path / 'key'
    key_file.write_text('secret\n')
    main(['run', 'never_ask', '--seeds', '1', '--hours', '.02', '--out', str(tmp_path), '--seed-key-file', str(key_file)])
    text = (tmp_path / 'run-episodes.csv').read_text() + capsys.readouterr().out
    assert 'secret' not in text and episode_seed(0, 'secret') not in text
    with (tmp_path / 'run-episodes.csv').open() as f:
        assert next(csv.DictReader(f))['seed'] == 'keyed:0'


def test_secret_seeds_differ_between_runs_and_a_broken_supervisor_is_left_out(tmp_path, capsys):
    rows = []
    for _ in range(2):
        main(['run', 'never_ask', '--seeds', '1', '--hours', '.05', '--out', str(tmp_path), '--secret-seeds'])
        with (tmp_path / 'run-episodes.csv').open() as f:
            rows.append(next(csv.DictReader(f)))
    assert rows[0]['seed'] == 'keyed:0' and rows[0] != rows[1]
    capsys.readouterr()
    with pytest.raises(SystemExit, match='no supervisor finished'):
        main(['run', 'hostile:Crash', '--seeds', '1', '--hours', '.05', '--out', str(tmp_path), '--isolate'])
    assert 'left out' in capsys.readouterr().err


def test_settings_can_be_changed_from_the_command_line(tmp_path, capsys):
    main(['run', 'never_ask', '--seeds', '1', '--hours', '.05', '--out', str(tmp_path),
          '--set', 'obstacles_per_hour=0', '--set', 'scan_failure=0'])
    assert 'obstacles_per_hour=0' in capsys.readouterr().out
    with (tmp_path / 'run-episodes.csv').open() as f:
        row = next(csv.DictReader(f))
    assert row.get('incidents_obstacle', '0') == '0' and row.get('incidents_scan_failure', '0') == '0'
    main(['run', 'never_ask', '--seeds', '1', '--out', str(tmp_path), '--set', 'hours=.05', '--set', 'robots=2'])
    assert '1 seeds x 0.05 h, 2 robots' in capsys.readouterr().out
    for bad in (['--set', 'nonsense=1'], ['--set', 'scan_failure=2'], ['--hours', '0'], ['--robots', '0'],
                ['--set', 'max_rescans=1.5'], ['--hours', '.05', '--set', 'hours=.1']):
        with pytest.raises(SystemExit):
            main(['run', 'never_ask', '--seeds', '1', '--out', str(tmp_path), *bad])


def test_secret_seeds_run_the_supervisor_isolated(tmp_path):
    main(['run', 'hostile:Snoop', '--seeds', '1', '--hours', '.01', '--out', str(tmp_path), '--secret-seeds'])
    with (tmp_path / 'run-episodes.csv').open() as f:
        row = next(csv.DictReader(f))
    assert row['supervisor'] == 'hostile:Snoop' and float(row['reported_files_here']) == 0
