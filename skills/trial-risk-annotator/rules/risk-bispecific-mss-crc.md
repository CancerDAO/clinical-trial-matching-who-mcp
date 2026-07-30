# Risk profile: Bispecific antibody in MSS CRC

## Authoritative classification correction

- Tarlatamab is a DLL3 x CD3 T-cell engager developed for DLL3-positive
  neuroendocrine cancers. It is not an anti-CTLA-4 x anti-PD-1 bispecific and
  must not be used as a CRC checkpoint-bispecific example.
- Cadonilimab (AK104) is an example of an anti-PD-1 x anti-CTLA-4 bispecific.
- If a later line conflicts with this correction, this section controls.

MSS (microsatellite stable) CRC is the immune-cold majority of metastatic CRC and historically responds poorly to single-agent PD-1/PD-L1 inhibitors. Bispecifics — particularly T-cell engagers — are a emerging strategy.

## Drugs / classes in this space

- **Anti-PD-1 × anti-VEGF bispecific**: ivonescimab (AK112) — has data in NSCLC, expanding to CRC
- **Anti-CTLA-4 × anti-PD-1 bispecific**: cadonilimab (AK104)-type architectures
- **CEA × CD3 BiTE**: cibisatamab (RG7802) — exploratory in mCRC
- **DLL3 × CD3**: not CRC-relevant
- **TIGIT bispecifics**: emerging

## CRC MSS context

- **Anti-PD-1 monotherapy in MSS mCRC**: ORR <5% (well established)
- **Anti-PD-1 + chemo + anti-VEGF**: marginal benefit in some subgroups
- **CRC MSS R1 overlap**: many patients have already had anti-PD-1 (especially in China where camrelizumab/sintilimab are commonly added to chemo backbones in 2L+) — bispecific trials may exclude prior PD-1 exposure

## Risk pattern

- **CRS (cytokine release syndrome)** for T-cell engagers — graded G1–G4. G1–G2 manageable with tocilizumab + supportive care; G3+ requires ICU.
- **On-target/off-tumor toxicity** for CEA × CD3 — diarrhea, colitis (CEA expressed in normal gut)
- **irAE** spectrum from PD-1 axis: hypothyroidism, pneumonitis, hepatitis, colitis
- **Ramp-up dosing required** — first cycles at low dose, escalation per protocol

## Patient-specific considerations

For a KRAS G12C MSS mCRC patient with prior PD-1 and anti-VEGF exposure:
- Bispecific anti-PD-1 × anti-VEGF would be redundant with prior treatment classes — unlikely to qualify as differentiated path
- Bispecific CEA × CD3 — novel mechanism, not previously exposed, but ORR data sparse in CRC
- If trial requires PD-1 naive, R1 will trigger from prior camrelizumab

## Output template (MSS CRC patient with prior PD-1)

```json
{
  "key": "bispecific_mss_crc_post_pd1",
  "mechanism": "Bispecific T-cell engager (CEA × CD3 / similar)",
  "cancer_context": "CRC MSS, post-PD-1",
  "risk_level": "high_uncertainty",
  "narrative": [
    "Bispecifics in MSS CRC are exploratory; ORR <20% in published Phase 1",
    "CRS likely: ramp-up dosing required, ICU on standby for G3+",
    "On-target/off-tumor: diarrhea/colitis if CEA-targeting",
    "R1 caveat: if trial excludes prior PD-1, patient's camrelizumab history triggers screening conversation"
  ]
}
```
