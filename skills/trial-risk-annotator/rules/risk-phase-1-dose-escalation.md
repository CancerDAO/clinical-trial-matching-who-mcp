# Risk profile: Phase 1 dose escalation (overlay)

Generic risk overlay for any trial in Phase 1 dose-escalation phase. Apply on top of mechanism-specific risk.

## Why an overlay

Phase 1a (escalation) cohorts assign patients to dose levels below the recommended Phase 2 dose (RP2D). Early cohorts may receive sub-therapeutic doses, raising the risk of disease progression while on study without therapeutic benefit.

## Decision factors

| Factor | Implication |
|---|---|
| Phase 1a (escalation) only | Patient may be in low-dose cohort — counsel transparently |
| Phase 1b (expansion at RP2D) | Patient gets recommended dose — efficacy expectations more representative |
| Phase 1/2 with both arms open | Patient should ask which arm is enrolling and whether RP2D cohort has slots |
| Adaptive design (BOIN, mTPI) | Faster escalation, less time in sub-therapeutic doses |
| 3+3 traditional escalation | Slower, but well-understood safety profile |

## Counsel patient

- Ask sponsor explicitly: "Is there a Phase 1b expansion cohort at the recommended dose currently enrolling?"
- If only Phase 1a is open, weigh the option against standard-of-care (which may have known efficacy, even if modest)
- Phase 1 trials usually have intensive monitoring schedules — biopsies, frequent labs, PK draws — patient time burden is higher

## Output template

```json
{
  "key": "phase_1_dose_escalation",
  "mechanism": "Phase 1 dose escalation overlay",
  "cancer_context": "any",
  "risk_level": "moderate",
  "narrative": [
    "Phase 1a escalation: patient may receive sub-therapeutic dose in early cohorts — disease progression risk",
    "Ask sponsor whether Phase 1b expansion at RP2D is currently enrolling",
    "Monitoring burden higher than Phase 2/3 (frequent labs, optional biopsies, PK draws)"
  ]
}
```

## Skip when

- Trial is Phase 2 / 3 — overlay not relevant
- Trial is Phase 1b only (expansion) — partial relevance, modify narrative
