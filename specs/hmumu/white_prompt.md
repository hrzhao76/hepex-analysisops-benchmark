# Task: Search for H -> mu+ mu- (VBF Channel)

## Objective
Analyze the ATLAS Open Data (Release 2025e-13tev-beta) to search for the Higgs boson decaying into a pair of muons ($H \rightarrow \mu^+ \mu^-$) produced via Vector Boson Fusion (VBF).

## Physics Context
The $H \rightarrow \mu^+ \mu^-$ decay is rare (branching ratio ~2e-4) and sits on a large Drell-Yan background. To improve sensitivity, we target the VBF production mode, characterized by two energetic forward "tagging" jets with a large rapidity gap and high invariant mass.

## Data & environment
- You will receive a list of local ROOT file paths.
- Use at most 1 file.
- You may inspect the ROOT schema (trees/branches) if needed.

## Analysis Steps

### 1. Event Selection
Implement the following cuts sequence. Record the number of events passing each step.
1. **Trigger**: Single muon trigger `trigM`.
2. **Trigger Match**: At least one muon matched to the trigger.
3. **Two Muons**: Exactly 2 muons (Type 13).
4. **Kinematics**: Both muons $p_T > 30$ GeV.
5. **Charge**: Opposite charge ($\sum q = 0$).
6. **MET**: $E_T^{miss} \le 80$ GeV (suppress $t\bar{t}$).
7. **Quality**: Medium ID, Loose Iso for both muons.
8. **Jet Veto (b-tag)**: To suppress $t\bar{t}$ background, require that no jets have a b-tagging quantile < 3 (i.e., `ak.sum(jet_btag_quantile < 3) == 0`).
9. **VBF Tagging**:
    - At least 2 jets with $p_T > 30$ GeV and $E > 30$ GeV.
    - $m_{jj} > 500$ GeV.
    - $|\Delta\eta_{jj}| > 3.0$ and opposite hemispheres ($\eta_1 \cdot \eta_2 < 0$).
    - Separation: $\Delta R(\mu, j) \ge 0.4$ for all combinations of muons and tagging jets.

### 2. Signal Extraction
Fit the dimuon invariant mass distribution ($m_{\mu\mu}$) in the range [110, 160] GeV.
- **Model**: Signal (Gaussian/Crystal Ball) + Background (Exponential/Polynomial).
- **Goal**: Extract the signal peak position ($m_H$) and significance.

## Expected Output
Return a JSON object with the following structure:
```json
{
  "status": "success",
  "cuts": [
    {"cut_id": "trig", "expression": "...", "description": "..."},
    ...
  ],
  "cutflow": [
    {"cut_id": "trig", "n_before": 1000, "n_after": 900},
    ...
  ],
  "fit_method": {
    "model": "Describe your model (e.g. Unbinned Likelihood with Gaussian signal)",
    "optimizer": "e.g. Minuit",
    "fit_range": [110, 160],
    "reasoning": "Explain WHY you chose this model and these cuts. Why VBF? Why veto b-jets?"
  },
  "fit_result": {
    "center": 125.0,
    "sigma": 2.5,
    "significance": 1.2
  }
}
```

## Guidance
- Briefly justify the fit model and fit range.
- IMPORTANT: Only report values that came from actual tool calls. Do not fabricate results.
- If you cannot complete, set status="error" and explain in "comments".
- Output JSON only, no markdown code blocks or extra text.
