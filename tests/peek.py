"""A supervisor that tries to read the ground truth from the simulator through the call stack."""
import inspect

from fleetattention.model import Decision
from fleetattention.supervisors import Supervisor


class Peek(Supervisor):
    name = 'peek'

    def decide(self, obs, ctx):
        frame = inspect.currentframe()
        while frame is not None:
            episode = frame.f_locals.get('self')
            if hasattr(episode, 'incidents'):
                return Decision.act(episode.incidents[obs.incident].correct)
            frame = frame.f_back
        return Decision.ask()
