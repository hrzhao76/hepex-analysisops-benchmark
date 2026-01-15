# Task: Search for H -> bb (VH 0-Lepton Channel)

## Objective
Analyze the ATLAS Open Data (Release 2025e-13tev-beta) to search for the Higgs boson decaying into a pair of b-quarks ($H \rightarrow b\bar{b}$) produced in association with a Z boson decaying to neutrinos ($Z \rightarrow \nu\bar{\nu}$). This is known as the "0-lepton" channel.

## Physics Context
The $H \rightarrow b\bar{b}$ decay has the largest branching ratio (~58%) but suffers from massive QCD backgrounds. The VH production mode allows us to trigger on large Missing Transverse Energy (MET) from the Z boson decay, significantly reducing background.

## Analysis Steps

### 1. Event Selection
Implement the following cuts sequence. Record the number of events passing each step.
1.  **Trigger**: MET Trigger (`trigMET`).
2.  **MET**: $E_T^{miss} > 150$ GeV (Key discriminator).
3.  **Lepton Veto**: 0 leptons (Electron/Muon) to select $Z \rightarrow \nu\nu$.
4.  **Jets**: Exactly 2 or 3 jets (Anti-kt 0.4, $p_T > 20$, $|\eta| < 2.5$).
5.  **b-tagging**: Exactly 2 b-tagged jets (quantile >= 4 implies tight tagging).
    - Leading b-jet $p_T > 45$ GeV.
6.  **HT**: scalar sum of jet $p_T > 120$ GeV (2 jets) or $> 150$ GeV (3 jets).
7.  **Angular Cuts** (to suppress QCD):
    - $\Delta\phi(b_1, b_2) < 140^\circ$.
    - $\Delta\phi(MET, bb) > 120^\circ$.
    - $min[\Delta\phi(MET, jets)] > 20^\circ$ (2 jets) or $> 30^\circ$ (3 jets).

### 2. Signal Extraction
Reconstruct the invariant mass of the two b-tagged jets ($m_{bb}$).
- **Model**: Fit or simply calculate the mass peak.
- **Goal**: Identify the Higgs peak around 125 GeV.

## Expected Output
Return a JSON object with the following structure:
```json
{
  "status": "success",
  "cuts": [
    {"cut_id": "met_150", "expression": "met > 150", "description": "..."},
    ...
  ],
  "cutflow": [
    {"cut_id": "met_150", "n_before": 1000, "n_after": 500},
    ...
  ],
  "fit_method": {
    "model": "Describe how you calculate/fit mass",
    "optimizer": "...",
    "fit_range": "...",
    "reasoning": "Explain the role of MET > 150 and Angular cuts in suppressing QCD."
  },
  "fit_result": {
    "center": 125.0,
    "sigma": 10.0,
    "significance": 1.0
  }
}
```
