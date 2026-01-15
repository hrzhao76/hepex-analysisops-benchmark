# Task: Top Quark Reconstruction (Semileptonic)

## Objective
Analyze ATLAS Open Data to identify Top-Antitop ($t\bar{t}$) pair production in the semileptonic channel. One top decays hadronically ($t \rightarrow bW \rightarrow b q\bar{q}'$), the other leptonically ($t \rightarrow bW \rightarrow b \ell \nu$).

## Physics Context
$t\bar{t}$ production is a dominant standard model process at the LHC. Reconstructing the top mass tests our understanding of jet energy scale and b-tagging. The challenge is "neutrino reconstruction" and "combinatoric ambiguity" (which jet goes where?).

## Analysis Steps

### 1. Event Selection
1.  **Trigger**: Single-lepton trigger.
2.  **Lepton**: Exactly 1 high-$p_T$ lepton (e/mu, $>25$ GeV).
3.  **MET**: $E_T^{miss} > 30$ GeV (Neutrino presence).
4.  **W Mass (Transverse)**: $M_T^W > 30$ GeV (Clean W candidate).
5.  **Jets**: At least 4 jets ($p_T > 25$ GeV).
6.  **b-tagging**: At least 2 b-tagged jets.

### 2. Top Reconstruction
Perform the following reconstruction steps:
1.  **Neutrino Pz**: Calculate longitudinal momentum of neutrino ($p_z^\nu$) by constraining $(p_\ell + p_\nu)^2 = m_W^2$. This yields a quadratic equation; pick the real, smaller $|p_z|$ solution.
2.  **Hadronic Top**: Identify 3 jets (including 1 b-jet) whose mass is closest to $m_{top}$ (172.5 GeV).
3.  **Leptonic Top**: Combine lepton, neutrino, and the other b-jet.
4.  **Mass**: Compute and report the mass of the reconstructed hadronic top.

## Expected Output
Return a JSON object with the following structure:
```json
{
  "status": "success",
  "cuts": [ ... ],
  "fit_method": {
    "model": "Reconstruction Algorithm",
    "reasoning": "Explain how you solved for neutrino Pz and how you handled jet combinatorics (e.g. minimizing chi-squared or mass diff)."
  },
  "fit_result": {
    "center": 172.5,
    "sigma": 15.0, # Broad peak due to jet resolution
    "significance": 10.0
  }
}
```
