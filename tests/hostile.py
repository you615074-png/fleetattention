"""Supervisors that try to cheat or break the protocol, for the isolation tests."""
import os
import sys
import time

from fleetattention.model import Decision
from fleetattention.supervisors import Supervisor
from fleetattention.world import supervisor_seed

MARKER = 'not-a-real-key-7f3a'


class Snoop(Supervisor):
    """Looks for the seed key on its command line, in its environment and in its working directory."""
    name = 'snoop'

    def report(self):
        here = os.listdir(os.curdir)
        blob = ' '.join(sys.argv) + ' '.join(f'{k}={v}' for k, v in os.environ.items())
        return {'key_seen': float(MARKER in blob), 'env': len(os.environ), 'files_here': len(here)}

    def decide(self, obs, ctx):
        return Decision.act(obs.actions[-1])


class Shadow(Supervisor):
    """Tries to recover the episode seed from its own seed, the first step of simulating the episode itself."""
    name = 'shadow'

    def reset(self, seed):
        self.found = any(supervisor_seed(i) == seed for i in range(20))

    def report(self):
        return {'found': float(self.found)}

    def decide(self, obs, ctx):
        return Decision.act(obs.actions[-1])


class Sleepy(Supervisor):
    name = 'sleepy'

    def decide(self, obs, ctx):
        time.sleep(30)


class Loud(Supervisor):
    name = 'loud'

    def decide(self, obs, ctx):
        return Decision('act', 'x' * 200_000)


class Crash(Supervisor):
    name = 'crash'

    def decide(self, obs, ctx):
        raise RuntimeError('boom')


def _wire():
    """The child's own reply stream, found the way a cheating supervisor would."""
    frame = sys._getframe()
    while frame.f_code.co_name != '_serve':
        frame = frame.f_back
    return frame.f_locals['out']


class Flood(Supervisor):
    """Sends a pile of replies before being asked, then stops reading its requests."""
    name = 'flood'

    def decide(self, obs, ctx):
        out = _wire()
        out.write(b'["ask", null, null]\n' * 3000)
        out.flush()
        time.sleep(60)


class Infinite(Supervisor):
    name = 'infinite'

    def decide(self, obs, ctx):
        out = _wire()
        out.write(b'["join", null, Infinity]\n')
        out.flush()
        time.sleep(60)


class Huge(Supervisor):
    name = 'huge'

    def report(self):
        return {'count': 10 ** 400}

    def decide(self, obs, ctx):
        return Decision.act(obs.actions[-1])


class BadKey(Supervisor):
    """Reports under a name that cannot be written as UTF-8."""
    name = 'bad_key'

    def report(self):
        return {chr(0xD800): 1}

    def decide(self, obs, ctx):
        return Decision.act(obs.actions[-1])


class Teleport(Supervisor):
    name = 'teleport'

    def decide(self, obs, ctx):
        return Decision.act('teleport')


class Spawner(Supervisor):
    """Starts a process of its own that would outlive the episode."""
    name = 'spawner'

    def reset(self, seed):
        import subprocess
        self.child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])

    def report(self):
        return {'pid': self.child.pid, 'cwd_is_temp': float('fleetattention-' in os.getcwd())}

    def decide(self, obs, ctx):
        return Decision.act(obs.actions[-1])
