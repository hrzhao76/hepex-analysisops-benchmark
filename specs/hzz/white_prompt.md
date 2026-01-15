# Task: Search for H -> ZZ* -> 4l (Golden Channel)

## Objective
Analyze the ATLAS Open Data to rediscover the Higgs boson in the "Golden Channel", where it decays into two Z bosons, which subsequently decay into four leptons ($H \rightarrow ZZ^* \rightarrow 4\ell$).

## Physics Context
This channel provides the cleanest signal with very high signal-to-background ratio and excellent mass resolution. The main backgrounds are non-resonant $ZZ^*$ production and $Z+jets$ (reducible).

## Analysis Steps

### 1. Event Selection
1.  **Trigger**: Single-lepton or Di-lepton triggers.
2.  **Four Leptons**: Select events with exactly 4 leptons (electrons or muons).
3.  **Kinematics**:
    - Leading lepton $p_T > 20$ GeV.
    - Sub-leading lepton $p_T > 15$ GeV.
    - 3rd lepton $p_T > 10$ GeV.
4.  **Charge & Flavor**:
    - Form two pairs of Same-Flavor Opposite-Sign (SFOS) leptons.
    - Allowed combinations: $4e$, $4\mu$, $2e2\mu$.
    - Net charge must be 0.
5.  **Z Candidates**:
    - **Lepton Pair 1 ($Z_1$)**: Mass closest to $m_Z$ (91.2 GeV). Limit: 50 < $m_{12}$ < 106 GeV.
    - **Lepton Pair 2 ($Z_2$)**: Remaining pair. Limit: 12 < $m_{34}$ < 115 GeV.

### 2. Signal Extraction
Reconstruct the four-lepton invariant mass ($m_{4\ell}$).
- **Model**: Fit with Gaussian/Crystal Ball (Signal) + Polynomial (Background).
- **Goal**: Find peak around 125 GeV.

## Expected Output
Return a JSON object with the following structure:
```json
{
  "status": "success",
  "cuts": [
    {"cut_id": "4lep", "expression": "n_lep == 4", "description": "..."},
    ...
  ],
  "cutflow": [ ... ],
  "fit_method": {
    "model": "...",
    "optimizer": "...",
    "fit_range": [80, 170],
    "reasoning": "Explain mechanism of pairing leptons into Z1 and Z2."
  },
  "fit_result": {
    "center": 125.0,
    "sigma": 2.0,
    "significance": 5.0
  }
}
```
