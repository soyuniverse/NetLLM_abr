"""Unit tests for the pluggable ABR speculative drafters.

soyun / speculative inference.  CPU only -- numpy, no torch, no GPU.

Covers the four things the refactor has to keep true:

1. ``mpc`` is a byte-for-byte regression against the frozen pre-refactor
   generator (``_reference_mpc_draft.py``).
2. ``repeat-last`` emits exactly ``last_action`` k times.
3. ``hybrid`` routes to the right proposer on both sides of both thresholds,
   boundaries included.
4. All three drafters go through the shared trajectory simulator and produce
   queue-usable ``predicted_state`` / ``predicted_return`` values.
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ABR_ROOT = os.path.join(REPO, 'adaptive_bitrate_streaming')
for path in (ABR_ROOT, HERE, os.path.join(REPO, 'abr_spec')):
    if path not in sys.path:
        sys.path.insert(0, path)

from baseline_special.utils.constants import BITRATE_LEVELS, TOTAL_VIDEO_CHUNK
from plm_special.speculative import (
    DRAFTERS,
    BaseDraftGenerator,
    HybridDraftGenerator,
    RepeatLastDraftGenerator,
    RobustMPCDraftGenerator,
    build_acceptance_plan,
    build_drafter,
    throughput_coefficient_of_variation,
    validate_speculative_observation,
)

import _reference_mpc_draft as reference


def sample_state(throughput=10.0, buffer_size=10.0, remaining=10.0):
    """Same fixture the upstream mpc tests use."""
    state = np.zeros((6, 6), dtype=np.float32)
    state[1, -1] = buffer_size / 10.0
    state[2, :] = throughput
    state[4, :] = 1.0
    state[5, -1] = remaining / 48.0
    return state


def state_with_throughputs(values, buffer_size=10.0, remaining=10.0):
    state = sample_state(buffer_size=buffer_size, remaining=remaining)
    state[2, :] = np.asarray(values, dtype=np.float32)
    return state


VIDEO_SIZES = np.full((BITRATE_LEVELS, 48), 1_000_000, dtype=np.float64)


class SharedSimulatorTest(unittest.TestCase):
    """Job (b): the trajectory simulator is drafter-independent."""

    def setUp(self):
        self.gen = RobustMPCDraftGenerator(VIDEO_SIZES, max_horizon=5)

    def test_injected_sequence_is_simulated_verbatim(self):
        actions = (2, 3, 2)
        rollout = self.gen.simulate_actions(
            actions=actions, state=sample_state(), last_bitrate=1,
            buffer_size=10.0, video_chunk_remain=10, target_return=5.0,
            timestep=7, bandwidth=10.0,
        )
        self.assertEqual(rollout.actions.tolist(), list(actions))
        self.assertEqual(rollout.timesteps.tolist(), [7, 8, 9])
        self.assertEqual(rollout.states.shape, (3, 6, 6))

    def test_every_drafter_shares_the_same_simulator(self):
        """Same actions + same inputs => identical trajectory, whatever the class."""
        actions = (1, 1, 2)
        kw = dict(actions=actions, state=sample_state(), last_bitrate=1,
                  buffer_size=10.0, video_chunk_remain=10, target_return=5.0,
                  timestep=0, bandwidth=10.0)
        rollouts = [cls(VIDEO_SIZES, max_horizon=5).simulate_actions(**kw)
                    for cls in (RobustMPCDraftGenerator, RepeatLastDraftGenerator,
                                HybridDraftGenerator)]
        for other in rollouts[1:]:
            np.testing.assert_array_equal(rollouts[0].states, other.states)
            np.testing.assert_array_equal(rollouts[0].returns, other.returns)
            np.testing.assert_array_equal(rollouts[0].predicted_buffers,
                                          other.predicted_buffers)
            np.testing.assert_array_equal(rollouts[0].predicted_rebuffers,
                                          other.predicted_rebuffers)

    def test_simulator_rejects_invalid_action_sequences(self):
        kw = dict(state=sample_state(), last_bitrate=0, buffer_size=10.0,
                  video_chunk_remain=10, target_return=1.0, timestep=0,
                  bandwidth=10.0)
        with self.assertRaises(ValueError):
            self.gen.simulate_actions(actions=(), **kw)
        with self.assertRaises(ValueError):
            self.gen.simulate_actions(actions=(BITRATE_LEVELS,), **kw)
        with self.assertRaises(ValueError):
            self.gen.simulate_actions(actions=(-1,), **kw)

    def test_simulator_refuses_to_run_past_the_end_of_the_video(self):
        with self.assertRaises(ValueError):
            self.gen.simulate_actions(
                actions=(0, 0, 0), state=sample_state(remaining=1),
                last_bitrate=0, buffer_size=10.0, video_chunk_remain=1,
                target_return=1.0, timestep=46, bandwidth=10.0,
            )

    def test_base_generator_has_no_proposer(self):
        with self.assertRaises(NotImplementedError):
            BaseDraftGenerator(VIDEO_SIZES).propose_actions(
                state=sample_state(), last_bitrate=0, buffer_size=10.0,
                chunk_index=0, bandwidth=10.0, rollout_length=3)


class RepeatLastDrafterTest(unittest.TestCase):
    def setUp(self):
        self.gen = RepeatLastDraftGenerator(VIDEO_SIZES, max_horizon=5)

    def test_emits_last_action_exactly_k_times(self):
        for last in range(BITRATE_LEVELS):
            for k in (1, 2, 3, 4, 5):
                rollout = self.gen.generate(
                    state=sample_state(), last_bitrate=last, buffer_size=10.0,
                    video_chunk_remain=20, target_return=5.0, timestep=0,
                    horizon=k,
                )
                self.assertEqual(rollout.actions.tolist(), [last] * k,
                                 msg=f'last={last} k={k}')
                self.assertEqual(rollout.length, k)
                self.gen.reset()

    def test_horizon_clipping_still_applies(self):
        rollout = self.gen.generate(
            state=sample_state(remaining=2), last_bitrate=4, buffer_size=10.0,
            video_chunk_remain=2, target_return=1.0, timestep=46, horizon=5,
        )
        self.assertEqual(rollout.actions.tolist(), [4, 4])
        self.assertEqual(rollout.timesteps.tolist(), [46, 47])

    def test_costs_no_search(self):
        """The proposer must not depend on video sizes, buffer or bandwidth."""
        a = self.gen.propose_actions(state=sample_state(), last_bitrate=3,
                                     buffer_size=0.1, chunk_index=0,
                                     bandwidth=0.01, rollout_length=3)
        b = self.gen.propose_actions(state=sample_state(), last_bitrate=3,
                                     buffer_size=99.0, chunk_index=10,
                                     bandwidth=99.0, rollout_length=3)
        self.assertEqual(a, b)
        self.assertEqual(a, (3, 3, 3))


class HybridRoutingTest(unittest.TestCase):
    """Thresholds: MPC iff buffer < B or CV >= C.  Boundaries included."""

    def setUp(self):
        self.gen = HybridDraftGenerator(VIDEO_SIZES, max_horizon=5,
                                        buffer_threshold=5.0, cv_threshold=0.30)

    def _steady(self):
        return state_with_throughputs([10.0] * 6)      # CV == 0

    def test_defaults_match_baseline6(self):
        gen = HybridDraftGenerator(VIDEO_SIZES)
        self.assertEqual(gen.buffer_threshold, 5.0)
        self.assertEqual(gen.cv_threshold, 0.30)

    def test_low_buffer_routes_to_mpc(self):
        self.assertEqual(self.gen.route(self._steady(), 4.999), 'mpc')

    def test_buffer_boundary_is_exclusive(self):
        # buffer_size < B routes to MPC, so exactly B must NOT.
        self.assertEqual(self.gen.route(self._steady(), 5.0), 'repeat-last')
        self.assertEqual(self.gen.route(self._steady(), 4.9999999), 'mpc')

    def test_high_buffer_steady_throughput_routes_to_repeat_last(self):
        self.assertEqual(self.gen.route(self._steady(), 25.0), 'repeat-last')

    def test_volatile_throughput_routes_to_mpc_even_with_a_full_buffer(self):
        volatile = state_with_throughputs([1.0, 20.0, 1.0, 20.0, 1.0, 20.0])
        self.assertGreaterEqual(
            throughput_coefficient_of_variation(volatile), 0.30)
        self.assertEqual(self.gen.route(volatile, 30.0), 'mpc')

    def test_cv_boundary_is_inclusive(self):
        # Build a state whose CV is exactly 0.30: values m*(1+-cv) in equal parts.
        cv = 0.30
        values = [10.0 * (1 - cv), 10.0 * (1 + cv)] * 3
        state = state_with_throughputs(values)
        self.assertAlmostEqual(throughput_coefficient_of_variation(state), cv,
                               places=12)
        self.assertEqual(self.gen.route(state, 30.0), 'mpc')     # >= C -> mpc
        just_under = state_with_throughputs(
            [10.0 * (1 - cv + 1e-6), 10.0 * (1 + cv - 1e-6)] * 3)
        self.assertLess(throughput_coefficient_of_variation(just_under), cv)
        self.assertEqual(self.gen.route(just_under, 30.0), 'repeat-last')

    def test_undefined_cv_is_not_volatile(self):
        """First chunk of an episode: <2 positive observations -> CV is None."""
        state = state_with_throughputs([0.0, 0.0, 0.0, 0.0, 0.0, 7.0])
        self.assertIsNone(throughput_coefficient_of_variation(state))
        self.assertEqual(self.gen.route(state, 30.0), 'repeat-last')
        # ...but the real first decision has buffer 4.0 s, which routes to MPC.
        self.assertEqual(self.gen.route(state, 4.0), 'mpc')

    def test_routed_proposals_equal_the_pure_drafters(self):
        mpc = RobustMPCDraftGenerator(VIDEO_SIZES, max_horizon=5)
        rep = RepeatLastDraftGenerator(VIDEO_SIZES, max_horizon=5)
        kw = dict(last_bitrate=2, chunk_index=0, bandwidth=10.0, rollout_length=3)
        low = self._steady()
        self.assertEqual(
            tuple(self.gen.propose_actions(state=low, buffer_size=1.0, **kw)),
            tuple(mpc.propose_actions(state=low, buffer_size=1.0, **kw)))
        self.assertEqual(self.gen.last_route, 'mpc')
        self.assertEqual(
            tuple(self.gen.propose_actions(state=low, buffer_size=30.0, **kw)),
            tuple(rep.propose_actions(state=low, buffer_size=30.0, **kw)))
        self.assertEqual(self.gen.last_route, 'repeat-last')

    def test_rejects_bad_thresholds(self):
        for kwargs in ({'buffer_threshold': -1.0}, {'cv_threshold': -0.1},
                       {'buffer_threshold': float('nan')},
                       {'cv_threshold': float('inf')}):
            with self.assertRaises(ValueError):
                HybridDraftGenerator(VIDEO_SIZES, **kwargs)


class ThroughputCVTest(unittest.TestCase):
    def test_matches_the_baseline6_analysis_statistic(self):
        """abr_spec/analyze_decisions.cv is what bucketed BASELINE6; agree with it."""
        from analyze_decisions import cv as analysis_cv
        for values in ([10.0] * 6,
                       [1.0, 20.0, 1.0, 20.0, 1.0, 20.0],
                       [0.0, 0.0, 3.0, 4.0, 5.0, 6.0],
                       [0.0, 0.0, 0.0, 0.0, 0.0, 7.0],
                       [0.5, 0.6, 0.55, 0.62, 0.58, 0.61]):
            state = state_with_throughputs(values)
            mine = throughput_coefficient_of_variation(state)
            theirs = analysis_cv([float(v) for v in state[2]])
            if theirs is None:
                self.assertIsNone(mine)
            else:
                self.assertAlmostEqual(mine, theirs, places=9, msg=str(values))


class MPCRefactorRegressionTest(unittest.TestCase):
    """The mpc path must be unchanged by the proposer/simulator split."""

    def _battery(self):
        rng = np.random.default_rng(20260902)
        sizes = rng.integers(200_000, 4_000_000, size=(BITRATE_LEVELS, 48)
                             ).astype(np.float64)
        cases = []
        for _ in range(60):
            remaining = int(rng.integers(1, 48))
            cases.append(dict(
                video_sizes=sizes,
                state=state_with_throughputs(
                    rng.uniform(0.2, 12.0, size=6),
                    buffer_size=float(rng.uniform(0.0, 30.0)),
                    remaining=remaining),
                last_bitrate=int(rng.integers(0, BITRATE_LEVELS)),
                buffer_size=float(rng.uniform(0.0, 30.0)),
                video_chunk_remain=remaining,
                target_return=float(rng.uniform(-2.0, 6.0)),
                timestep=int(rng.integers(0, 47)),
                horizon=int(rng.integers(1, 6)),
            ))
        return cases

    def test_identical_to_frozen_pre_refactor_generator(self):
        checked = 0
        for case in self._battery():
            sizes = case.pop('video_sizes')
            new = RobustMPCDraftGenerator(sizes, max_horizon=5)
            old = reference.RobustMPCDraftGenerator(sizes, max_horizon=5)
            # identical predictor history on both sides
            for gen in (new, old):
                gen.observe(case['state'])
            try:
                got = new.generate(**case)
            except ValueError as exc:
                with self.assertRaises(ValueError):
                    old.generate(**case)
                self.assertIsInstance(exc, ValueError)
                continue
            want = old.generate(**case)
            np.testing.assert_array_equal(got.actions, want.actions)
            np.testing.assert_array_equal(got.states, want.states)
            np.testing.assert_array_equal(got.returns, want.returns)
            np.testing.assert_array_equal(got.timesteps, want.timesteps)
            np.testing.assert_array_equal(got.predicted_buffers,
                                          want.predicted_buffers)
            np.testing.assert_array_equal(got.predicted_rewards,
                                          want.predicted_rewards)
            np.testing.assert_array_equal(got.predicted_rebuffers,
                                          want.predicted_rebuffers)
            self.assertEqual(got.predicted_bandwidth, want.predicted_bandwidth)
            checked += 1
        self.assertGreater(checked, 40, 'battery degenerated into error cases')

    def test_reward_transform_and_preobserved_bandwidth_also_match(self):
        sizes = np.full((BITRATE_LEVELS, 48), 1_500_000, dtype=np.float64)
        new = RobustMPCDraftGenerator(sizes, max_horizon=5)
        old = reference.RobustMPCDraftGenerator(sizes, max_horizon=5)
        state = sample_state(throughput=3.0)
        kw = dict(state=state, last_bitrate=2, buffer_size=8.0,
                  video_chunk_remain=12, target_return=4.0, timestep=5,
                  horizon=4, reward_transform=lambda r: r / 10.0,
                  predicted_bandwidth=2.75)
        got, want = new.generate(**kw), old.generate(**kw)
        np.testing.assert_array_equal(got.actions, want.actions)
        np.testing.assert_array_equal(got.returns, want.returns)
        self.assertEqual(new.past_bandwidth_estimates, old.past_bandwidth_estimates)

    def test_predictor_state_evolves_identically(self):
        sizes = np.full((BITRATE_LEVELS, 48), 900_000, dtype=np.float64)
        new = RobustMPCDraftGenerator(sizes, max_horizon=5)
        old = reference.RobustMPCDraftGenerator(sizes, max_horizon=5)
        rng = np.random.default_rng(7)
        for _ in range(25):
            state = state_with_throughputs(rng.uniform(0.5, 9.0, size=6))
            self.assertAlmostEqual(new.observe(state), old.observe(state), places=15)
        self.assertEqual(new.past_errors, old.past_errors)
        self.assertEqual(new.past_bandwidth_estimates, old.past_bandwidth_estimates)


class QueueContractTest(unittest.TestCase):
    """Every drafter must still feed rl_policy's queue and the tolerance check."""

    def _rollout(self, gen):
        return gen.generate(
            state=sample_state(buffer_size=12.0), last_bitrate=2,
            buffer_size=12.0, video_chunk_remain=20, target_return=5.0,
            timestep=4, horizon=3,
        )

    def test_all_drafters_produce_queue_entries_and_validate(self):
        for name, cls in DRAFTERS.items():
            gen = cls(VIDEO_SIZES, max_horizon=5)
            rollout = self._rollout(gen)
            self.assertEqual(rollout.length, 3, msg=name)
            self.assertEqual(rollout.states.shape, (3, 6, 6), msg=name)
            self.assertTrue(np.all(np.isfinite(rollout.states)), msg=name)
            self.assertTrue(np.all(np.isfinite(rollout.returns)), msg=name)
            self.assertTrue(np.all(np.isfinite(rollout.predicted_buffers)), msg=name)
            for action in rollout.actions.tolist():
                self.assertIn(action, range(BITRATE_LEVELS), msg=name)
            # exactly the queue entry rl_policy.sample_speculative builds
            for index, action in enumerate(rollout.actions.tolist()):
                entry = {
                    'action': int(action),
                    'predicted_state': rollout.states[index].copy(),
                    'predicted_return': float(rollout.returns[index]),
                    'source': 'accepted',
                }
                self.assertEqual(entry['predicted_state'].shape, (6, 6), msg=name)
                validation = validate_speculative_observation(
                    observed_state=entry['predicted_state'],
                    predicted_state=entry['predicted_state'],
                    observed_return=entry['predicted_return'],
                    predicted_return=entry['predicted_return'],
                    buffer_tolerance_seconds=1.0,
                    state_tolerance=0.25,
                    return_tolerance=0.01,
                )
                self.assertTrue(validation.valid, msg=f'{name}[{index}]')

    def test_acceptance_plan_accepts_every_drafter_output(self):
        for name, cls in DRAFTERS.items():
            rollout = self._rollout(cls(VIDEO_SIZES, max_horizon=5))
            plan = build_acceptance_plan(rollout.actions, rollout.actions)
            self.assertTrue(plan.fully_accepted, msg=name)
            self.assertEqual(plan.accepted_count, rollout.length, msg=name)

    def test_first_predicted_state_is_the_observed_state(self):
        for name, cls in DRAFTERS.items():
            rollout = self._rollout(cls(VIDEO_SIZES, max_horizon=5))
            np.testing.assert_allclose(
                rollout.states[0], sample_state(buffer_size=12.0), rtol=0, atol=0,
                err_msg=name)

    def test_build_drafter_rejects_unknown_names(self):
        with self.assertRaises(ValueError):
            build_drafter('nope', '/does/not/matter')


class DrafterSelectTest(unittest.TestCase):
    """The wrapper-side injection that keeps run_plm.py unmodified."""

    def setUp(self):
        import plm_special.speculative.mpc_draft as mpc_mod
        self.mod = mpc_mod
        # from_video_size_dir is inherited from BaseDraftGenerator, so it is
        # normally ABSENT from the subclass __dict__; the patch shadows it there.
        self.had_own = ('from_video_size_dir'
                        in mpc_mod.RobustMPCDraftGenerator.__dict__)
        self.original = mpc_mod.RobustMPCDraftGenerator.__dict__.get(
            'from_video_size_dir')

    def tearDown(self):
        self._restore()

    def _restore(self):
        if self.had_own:
            self.mod.RobustMPCDraftGenerator.from_video_size_dir = self.original
        else:
            try:
                delattr(self.mod.RobustMPCDraftGenerator, 'from_video_size_dir')
            except AttributeError:
                pass

    def test_from_video_size_dir_is_inherited_not_overridden(self):
        """The patch has exactly one shadowing site, which is why it is reversible."""
        self.assertFalse(self.had_own)
        self.assertIn('from_video_size_dir', self.mod.BaseDraftGenerator.__dict__)

    def test_mpc_installs_no_patch(self):
        import drafter_select
        info = drafter_select.install('mpc')
        self.assertFalse(info['patched'])
        self.assertNotIn('from_video_size_dir',
                         self.mod.RobustMPCDraftGenerator.__dict__)

    def test_patch_redirects_the_single_construction_site(self):
        import drafter_select
        for name, expected in (('repeat-last', self.mod.RepeatLastDraftGenerator),
                               ('hybrid', self.mod.HybridDraftGenerator)):
            self._restore()
            info = drafter_select.install(name, buffer_threshold=7.0,
                                          cv_threshold=0.4)
            self.assertTrue(info['patched'])
            # run_plm.py's exact call, with load_video_sizes stubbed out
            captured = {}

            def fake_load(_dir, _sizes=VIDEO_SIZES):
                captured['called'] = True
                return _sizes

            real_load = self.mod.load_video_sizes
            self.mod.load_video_sizes = fake_load
            try:
                gen = self.mod.RobustMPCDraftGenerator.from_video_size_dir(
                    '/video/sizes', max_horizon=3)
            finally:
                self.mod.load_video_sizes = real_load
            self.assertTrue(captured.get('called'))
            self.assertIsInstance(gen, expected)
            self.assertEqual(gen.max_horizon, 3)
            if name == 'hybrid':
                self.assertEqual(gen.buffer_threshold, 7.0)
                self.assertEqual(gen.cv_threshold, 0.4)

    def test_rejects_unknown_drafter(self):
        import drafter_select
        with self.assertRaises(ValueError):
            drafter_select.install('bogus')


if __name__ == '__main__':
    unittest.main()
