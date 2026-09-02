"""Draft generators for ABR speculative inference.

A draft generator does two separable jobs:

1. **propose** a short sequence of future bitrate decisions, and
2. **simulate** the state / buffer / return trajectory that sequence implies.

Only (1) is a policy choice.  (2) is what the tolerance check in
``acceptance.validate_speculative_observation`` compares the real observation
against, so every drafter must produce it the same way.  The two are therefore
split: :class:`BaseDraftGenerator` owns the robust throughput predictor and the
shared trajectory simulator (:meth:`BaseDraftGenerator.simulate_actions`), and a
subclass only supplies :meth:`propose_actions`.

Three proposers ship here:

``RobustMPCDraftGenerator``
    NetLLM's Robust-MPC baseline: brute-force the ``6^k`` valid bitrate
    sequences and keep the highest-scoring one.  Default, unchanged behaviour.
``RepeatLastDraftGenerator``
    Repeat the last executed bitrate ``k`` times.  Zero CPU cost.
``HybridDraftGenerator``
    MPC when the buffer is short or throughput is volatile, repeat-last
    otherwise.

The measurement behind the last two (BASELINE6, 4,700 decisions over 100
fcc-test traces, `results/soyun/baseline6_20260902/`): the MPC proposal matches
the LoRA policy's own next action **12.84 %** of the time, while simply
repeating the last action matches it **93.30 %** of the time -- the policy's
action autocorrelation is 92.46 %.  Mean accepted prefix is 0.180 for MPC vs
1.457 for repeat-last.  MPC only wins where physics forces the action: buffer
< 5 s (43.0 % match) or throughput coefficient of variation >= 0.30 (40.9 %),
which is where ``HybridDraftGenerator``'s default thresholds come from.
"""

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np

from baseline_special.utils.constants import (
    BITRATE_LEVELS,
    BUFFER_NORM_FACTOR,
    CHUNK_TIL_VIDEO_END_CAP,
    MAX_VIDEO_BIT_RATE,
    REBUF_PENALTY,
    SMOOTH_PENALTY,
    TOTAL_VIDEO_CHUNK,
    VIDEO_BIT_RATE,
)


@dataclass
class MPCDraftRollout:
    states: np.ndarray
    actions: np.ndarray
    returns: np.ndarray
    timesteps: np.ndarray
    predicted_bandwidth: float
    predicted_buffers: np.ndarray
    predicted_rewards: np.ndarray
    predicted_rebuffers: np.ndarray

    @property
    def length(self):
        return int(self.actions.shape[0])


def load_video_sizes(video_size_dir):
    """Load NetLLM's six per-quality chunk-size files into ``[6, chunks]``."""
    video_size_dir = Path(video_size_dir)
    rows = []
    for bitrate in range(BITRATE_LEVELS):
        path = video_size_dir / f'video_size_{bitrate}'
        with path.open() as f:
            rows.append([int(line.split()[0]) for line in f if line.strip()])
    lengths = {len(row) for row in rows}
    if len(lengths) != 1:
        raise ValueError('all bitrate levels must contain the same chunk count')
    return np.asarray(rows, dtype=np.float64)


def resolve_state(state):
    """Reduce a torch/numpy ABR state of any leading batch shape to ``[6,6]``."""
    if hasattr(state, 'detach'):
        state = state.detach().cpu().numpy()
    state = np.asarray(state, dtype=np.float64)
    while state.ndim > 2 and state.shape[0] == 1:
        state = state[0]
    if state.shape != (6, 6):
        raise ValueError(f'state must resolve to shape [6,6], got {state.shape}')
    return state


def throughput_coefficient_of_variation(state):
    """Population CV of the positive throughput observations in the state.

    ``None`` when fewer than two positive observations exist (the first chunks
    of an episode).  This is the exact statistic
    ``abr_spec/analyze_decisions.py`` used to bucket BASELINE6's decisions, so
    ``HybridDraftGenerator``'s threshold means the same thing as the number in
    that analysis.
    """
    row = resolve_state(state)[2]
    values = [float(v) for v in row if v > 0]
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean <= 0:
        return None
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return float(np.sqrt(variance)) / mean


# ---------------------------------------------------------------------------
# Robust-MPC action proposal.  Kept as free functions so both
# RobustMPCDraftGenerator and HybridDraftGenerator can call the identical code.
# ---------------------------------------------------------------------------

def mpc_valid_sequences(last_bitrate, horizon):
    """Yield bitrate sequences that never jump more than one level per chunk."""
    for sequence in product(range(BITRATE_LEVELS), repeat=horizon):
        previous = int(last_bitrate)
        valid = True
        for bitrate in sequence:
            if abs(bitrate - previous) > 1:
                valid = False
                break
            previous = bitrate
        if valid:
            yield sequence


def mpc_sequence_score(video_sizes, sequence, chunk_index, buffer_size, bandwidth,
                       last_bitrate):
    """NetLLM's MPC utility for one candidate sequence."""
    score = 0.0
    current_buffer = float(buffer_size)
    previous = int(last_bitrate)
    for offset, action in enumerate(sequence):
        size = video_sizes[action, chunk_index + offset]
        download_time = (size / 1_000_000.0) / bandwidth
        rebuffer = max(download_time - current_buffer, 0.0)
        current_buffer = max(current_buffer - download_time, 0.0) + 4.0
        score += (
            VIDEO_BIT_RATE[action] / 1000.0
            - REBUF_PENALTY * rebuffer
            - SMOOTH_PENALTY
            * abs(VIDEO_BIT_RATE[action] - VIDEO_BIT_RATE[previous])
            / 1000.0
        )
        previous = action
    return score


def mpc_best_sequence(video_sizes, last_bitrate, buffer_size, chunk_index,
                      bandwidth, rollout_length):
    """Brute-force the valid sequences and return the highest-scoring one."""
    # Preserve the baseline's ``reward >= max_reward`` tie behavior.
    best_sequence = None
    best_score = -float('inf')
    for sequence in mpc_valid_sequences(last_bitrate, rollout_length):
        score = mpc_sequence_score(
            video_sizes, sequence, chunk_index, buffer_size, bandwidth, last_bitrate
        )
        if score >= best_score:
            best_sequence = sequence
            best_score = score
    return best_sequence


class BaseDraftGenerator:
    """Robust throughput predictor + shared trajectory simulator.

    Subclasses implement :meth:`propose_actions`.  Everything a queue entry is
    validated against -- ``predicted_state``/``predicted_return`` -- comes from
    :meth:`simulate_actions` and is therefore identical across drafters.
    """

    def __init__(self, video_sizes, max_horizon=5):
        video_sizes = np.asarray(video_sizes, dtype=np.float64)
        if video_sizes.ndim != 2 or video_sizes.shape[0] != BITRATE_LEVELS:
            raise ValueError(
                f'video_sizes must have shape [{BITRATE_LEVELS}, chunks]'
            )
        if (
            isinstance(max_horizon, bool)
            or not isinstance(max_horizon, int)
            or not 1 <= max_horizon <= 5
        ):
            raise ValueError('max_horizon must be an integer from 1 to 5')
        self.video_sizes = video_sizes
        self.max_horizon = max_horizon
        self.past_errors = []
        self.past_bandwidth_estimates = []

    @classmethod
    def from_video_size_dir(cls, video_size_dir, max_horizon=5, **kwargs):
        return cls(load_video_sizes(video_size_dir), max_horizon=max_horizon,
                   **kwargs)

    def reset(self):
        self.past_errors.clear()
        self.past_bandwidth_estimates.clear()

    @staticmethod
    def _state_array(state):
        return resolve_state(state)

    def observe(self, state):
        """Record one real throughput observation and return its robust forecast."""
        state = self._state_array(state)
        measured = float(state[2, -1])
        if self.past_bandwidth_estimates and measured > 0:
            error = abs(self.past_bandwidth_estimates[-1] - measured) / measured
        else:
            error = 0.0
        self.past_errors.append(error)

        bandwidths = state[2, -5:]
        bandwidths = bandwidths[bandwidths > 0]
        if bandwidths.size == 0:
            raise ValueError('at least one positive throughput observation is required')
        harmonic = float(bandwidths.size / np.sum(1.0 / bandwidths))
        max_error = max(self.past_errors[-5:])
        self.past_bandwidth_estimates.append(harmonic)
        return harmonic / (1.0 + max_error)

    def predict_bandwidth(self, state):
        """Backward-compatible alias for observing one real decision state."""
        return self.observe(state)

    def _transition(self, state, action, chunk_index, buffer_size, bandwidth, remaining):
        chunk_size = self.video_sizes[action, chunk_index]
        download_time = (chunk_size / 1_000_000.0) / bandwidth
        rebuffer = max(download_time - buffer_size, 0.0)
        next_buffer = max(buffer_size - download_time, 0.0) + 4.0
        next_remaining = max(float(remaining) - 1.0, 0.0)

        next_state = np.roll(state, -1, axis=-1).copy()
        next_state[0, -1] = VIDEO_BIT_RATE[action] / MAX_VIDEO_BIT_RATE
        next_state[1, -1] = next_buffer / BUFFER_NORM_FACTOR
        next_state[2, -1] = bandwidth
        next_state[3, -1] = download_time / BUFFER_NORM_FACTOR
        next_chunk_index = chunk_index + 1
        if next_chunk_index < self.video_sizes.shape[1]:
            next_state[4, :BITRATE_LEVELS] = (
                self.video_sizes[:, next_chunk_index] / 1_000_000.0
            )
        else:
            next_state[4, :BITRATE_LEVELS] = 0.0
        next_state[5, -1] = (
            min(next_remaining, CHUNK_TIL_VIDEO_END_CAP)
            / CHUNK_TIL_VIDEO_END_CAP
        )
        return next_state, next_buffer, download_time, rebuffer

    # -- job (b): trajectory simulation, shared by every drafter --------------
    def simulate_actions(
        self,
        actions,
        state,
        last_bitrate,
        buffer_size,
        video_chunk_remain,
        target_return,
        timestep,
        bandwidth,
        reward_transform=None,
    ):
        """Simulate the state/buffer/return trajectory of an injected sequence.

        This is the half of drafting that speculation's correctness depends on:
        ``rollout.states[i]`` and ``rollout.returns[i]`` become a queue entry's
        ``predicted_state`` / ``predicted_return`` and are what the tolerance
        check compares the next real observation against.  It is deliberately
        independent of *how* ``actions`` was chosen.
        """
        state = self._state_array(state)
        actions = tuple(int(action) for action in actions)
        if not actions:
            raise ValueError('actions must contain at least one bitrate decision')
        if any(not 0 <= action < BITRATE_LEVELS for action in actions):
            raise ValueError('every drafted action must be a valid bitrate level')
        chunk_index = int(TOTAL_VIDEO_CHUNK - video_chunk_remain)
        if chunk_index + len(actions) > self.video_sizes.shape[1]:
            raise ValueError('drafted sequence runs past the end of the video')
        reward_transform = reward_transform or (lambda reward: reward)

        states = []
        returns = []
        buffers = []
        rewards = []
        rebuffers = []
        current_state = state.copy()
        current_buffer = float(buffer_size)
        current_return = float(target_return)
        previous = int(last_bitrate)
        remaining = float(video_chunk_remain)
        for offset, action in enumerate(actions):
            states.append(current_state.copy())
            returns.append(current_return)
            next_state, next_buffer, _, rebuffer = self._transition(
                current_state,
                action,
                chunk_index + offset,
                current_buffer,
                bandwidth,
                remaining,
            )
            reward = (
                VIDEO_BIT_RATE[action] / 1000.0
                - REBUF_PENALTY * rebuffer
                - SMOOTH_PENALTY
                * abs(VIDEO_BIT_RATE[action] - VIDEO_BIT_RATE[previous])
                / 1000.0
            )
            rewards.append(reward)
            rebuffers.append(rebuffer)
            buffers.append(next_buffer)
            current_return -= float(reward_transform(reward))
            current_state = next_state
            current_buffer = next_buffer
            previous = action
            remaining -= 1.0

        return MPCDraftRollout(
            states=np.asarray(states, dtype=np.float32),
            actions=np.asarray(actions, dtype=np.int64),
            returns=np.asarray(returns, dtype=np.float32),
            timesteps=np.arange(timestep, timestep + len(actions), dtype=np.int64),
            predicted_bandwidth=bandwidth,
            predicted_buffers=np.asarray(buffers, dtype=np.float32),
            predicted_rewards=np.asarray(rewards, dtype=np.float32),
            predicted_rebuffers=np.asarray(rebuffers, dtype=np.float32),
        )

    # -- job (a): action proposal, the only part a drafter changes -----------
    def propose_actions(self, state, last_bitrate, buffer_size, chunk_index,
                        bandwidth, rollout_length):
        raise NotImplementedError

    def generate(
        self,
        state,
        last_bitrate,
        buffer_size,
        video_chunk_remain,
        target_return,
        timestep,
        horizon=None,
        reward_transform=None,
        predicted_bandwidth=None,
    ):
        """Return decision states and drafted actions for up to ``horizon`` chunks."""
        state = self._state_array(state)
        if not 0 <= int(last_bitrate) < BITRATE_LEVELS:
            raise ValueError('last_bitrate is outside the ABR action range')
        requested = self.max_horizon if horizon is None else int(horizon)
        if requested <= 0:
            raise ValueError('horizon must be positive')
        chunk_index = int(TOTAL_VIDEO_CHUNK - video_chunk_remain)
        available = min(
            int(video_chunk_remain),
            self.video_sizes.shape[1] - chunk_index,
        )
        rollout_length = min(requested, self.max_horizon, available)
        if rollout_length <= 0:
            raise ValueError('no video chunks remain for MPC drafting')

        bandwidth = (
            self.observe(state)
            if predicted_bandwidth is None
            else float(predicted_bandwidth)
        )
        if not np.isfinite(bandwidth) or bandwidth <= 0:
            raise ValueError('predicted_bandwidth must be finite and positive')

        actions = self.propose_actions(
            state=state,
            last_bitrate=int(last_bitrate),
            buffer_size=buffer_size,
            chunk_index=chunk_index,
            bandwidth=bandwidth,
            rollout_length=rollout_length,
        )
        return self.simulate_actions(
            actions=actions,
            state=state,
            last_bitrate=last_bitrate,
            buffer_size=buffer_size,
            video_chunk_remain=video_chunk_remain,
            target_return=target_return,
            timestep=timestep,
            bandwidth=bandwidth,
            reward_transform=reward_transform,
        )


class RobustMPCDraftGenerator(BaseDraftGenerator):
    """Generate a short robust-MPC trajectory using NetLLM state semantics."""

    name = 'mpc'

    @staticmethod
    def _valid_sequences(last_bitrate, horizon):
        return mpc_valid_sequences(last_bitrate, horizon)

    def _sequence_score(self, sequence, chunk_index, buffer_size, bandwidth,
                        last_bitrate):
        return mpc_sequence_score(self.video_sizes, sequence, chunk_index,
                                  buffer_size, bandwidth, last_bitrate)

    def propose_actions(self, state, last_bitrate, buffer_size, chunk_index,
                        bandwidth, rollout_length):
        return mpc_best_sequence(self.video_sizes, last_bitrate, buffer_size,
                                 chunk_index, bandwidth, rollout_length)


class RepeatLastDraftGenerator(BaseDraftGenerator):
    """Draft the last executed bitrate ``k`` times.

    Costs nothing to compute and, on BASELINE6's trace, agrees with the LoRA
    policy's next action 93.30 % of the time (mean accepted prefix 1.457 of 3,
    against MPC's 0.180).
    """

    name = 'repeat-last'

    def propose_actions(self, state, last_bitrate, buffer_size, chunk_index,
                        bandwidth, rollout_length):
        return (int(last_bitrate),) * rollout_length


class HybridDraftGenerator(BaseDraftGenerator):
    """MPC where physics forces the action, repeat-last everywhere else.

    Routes to MPC when ``buffer_size < buffer_threshold`` **or**
    ``throughput CV >= cv_threshold``; otherwise repeats the last action.  The
    defaults (5.0 s, 0.30) are the two BASELINE6 buckets where MPC's 1-step
    match rate rises to 43.0 % / 40.9 % from a 9-11 % baseline elsewhere.

    An undefined CV (fewer than two positive throughput observations, i.e. the
    first chunk of an episode) is treated as *not* volatile; those decisions are
    already routed to MPC by the buffer test, whose starting value is 4.0 s.

    ``last_route`` records which branch the most recent proposal took, for
    post-hoc attribution.
    """

    name = 'hybrid'

    def __init__(self, video_sizes, max_horizon=5, buffer_threshold=5.0,
                 cv_threshold=0.30):
        super().__init__(video_sizes, max_horizon=max_horizon)
        if not np.isfinite(buffer_threshold) or buffer_threshold < 0:
            raise ValueError('buffer_threshold must be finite and non-negative')
        if not np.isfinite(cv_threshold) or cv_threshold < 0:
            raise ValueError('cv_threshold must be finite and non-negative')
        self.buffer_threshold = float(buffer_threshold)
        self.cv_threshold = float(cv_threshold)
        self.last_route = None

    def route(self, state, buffer_size):
        """Return ``'mpc'`` or ``'repeat-last'`` for this decision."""
        if float(buffer_size) < self.buffer_threshold:
            return 'mpc'
        cv = throughput_coefficient_of_variation(state)
        if cv is not None and cv >= self.cv_threshold:
            return 'mpc'
        return 'repeat-last'

    def propose_actions(self, state, last_bitrate, buffer_size, chunk_index,
                        bandwidth, rollout_length):
        self.last_route = self.route(state, buffer_size)
        if self.last_route == 'mpc':
            return mpc_best_sequence(self.video_sizes, last_bitrate, buffer_size,
                                     chunk_index, bandwidth, rollout_length)
        return (int(last_bitrate),) * rollout_length


DRAFTERS = {
    'mpc': RobustMPCDraftGenerator,
    'repeat-last': RepeatLastDraftGenerator,
    'hybrid': HybridDraftGenerator,
}


def build_drafter(name, video_size_dir, max_horizon=5, **kwargs):
    """Construct one of ``DRAFTERS`` from a NetLLM video-size directory."""
    if name not in DRAFTERS:
        raise ValueError(
            f'unknown drafter {name!r}; choose from {sorted(DRAFTERS)}'
        )
    return DRAFTERS[name].from_video_size_dir(
        video_size_dir, max_horizon=max_horizon, **kwargs
    )
