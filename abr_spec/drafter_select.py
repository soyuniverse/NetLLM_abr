#!/usr/bin/env python3
"""abr_spec/drafter_select.py -- choose the speculative drafter without touching run_plm.py.

soyun / speculative inference.

``run_plm.py`` builds the drafter with one hard-coded call
(``run_plm.py:435-439``)::

    draft_generator = None
    if args.speculative_draft_steps > 0:
        draft_generator = RobustMPCDraftGenerator.from_video_size_dir(
            video_size_dir, max_horizon=args.speculative_draft_steps
        )

``run_plm.py`` is **not** modifiable, so the drafter choice cannot become a
``run_plm`` CLI flag.  Instead the flag lives on the wrapper
(``abr_spec/run_wrapped.py --speculative-drafter ...``) and this module
redirects that single construction site by replacing the **classmethod**
``RobustMPCDraftGenerator.from_video_size_dir`` before ``runpy`` executes
``run_plm.py``.  ``run_plm`` does ``from plm_special.speculative.mpc_draft
import RobustMPCDraftGenerator`` at import time, which binds the class object
itself, so a classmethod replacement on that object is seen by ``run_plm``
regardless of import order.

Nothing else is intercepted: the returned object is a real
``BaseDraftGenerator`` subclass with the same ``generate`` / ``observe`` /
``reset`` contract, so ``rl_policy`` cannot tell the difference.

``--speculative-drafter mpc`` (the default) installs **no patch at all** --
the mpc path is then bit-for-bit the upstream one.
"""

CHOICES = ('mpc', 'repeat-last', 'hybrid')

_INSTALLED = None


def install(drafter='mpc', buffer_threshold=5.0, cv_threshold=0.30):
    """Redirect run_plm.py's drafter construction.  Returns a provenance dict."""
    global _INSTALLED
    if drafter not in CHOICES:
        raise ValueError(f'unknown drafter {drafter!r}; choose from {list(CHOICES)}')

    info = {'drafter': drafter, 'patched': False,
            'buffer_threshold': None, 'cv_threshold': None}
    if drafter == 'mpc':
        print('[drafter_select] drafter=mpc -- no patch installed '
              '(upstream construction path untouched)')
        _INSTALLED = info
        return info

    import plm_special.speculative.mpc_draft as mpc_mod

    target = mpc_mod.DRAFTERS[drafter]
    kwargs = {}
    if drafter == 'hybrid':
        kwargs = {'buffer_threshold': float(buffer_threshold),
                  'cv_threshold': float(cv_threshold)}
        info['buffer_threshold'] = kwargs['buffer_threshold']
        info['cv_threshold'] = kwargs['cv_threshold']

    def from_video_size_dir(cls, video_size_dir, max_horizon=5, **extra):
        merged = dict(kwargs)
        merged.update(extra)
        return target.from_video_size_dir(video_size_dir, max_horizon=max_horizon,
                                          **merged)

    mpc_mod.RobustMPCDraftGenerator.from_video_size_dir = classmethod(
        from_video_size_dir)
    info['patched'] = True
    info['class'] = target.__name__
    print(f'[drafter_select] drafter={drafter} -> {target.__name__}'
          + (f' (buffer<{kwargs["buffer_threshold"]}s or CV>={kwargs["cv_threshold"]})'
             if kwargs else ''))
    _INSTALLED = info
    return info


def installed():
    return _INSTALLED
