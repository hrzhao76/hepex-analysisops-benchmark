# Task: WZ Diboson Production (3-Lepton Channel)

## Objective
Analyze ATLAS Open Data to study the Standard Model production of $WZ$ pairs, where $Z \rightarrow \ell\ell$ and $W \rightarrow \ell\nu$, resulting in a final state with 3 leptons and missing energy.

## Physics Context
This process allows measuring the WZ production cross-section and testing the electroweak gauge structure (trilinear gauge couplings). It is a major background for other 3-lepton searches (like SUSY).

## Analysis Steps

### 1. Event Selection
1.  **Trigger**: Dilepton or single-lepton triggers.
2.  **Leptons**: Exactly 3 leptons (e/mu).
    - $p_T$ thresholds: Lepton 1 > 20, Lepton 2 > 15, Lepton 3 > 10 GeV.
3.  **Quality**: Tight ID, Isolation.
4.  **Z Selection**: Identify a pair of Same-Flavor Opposite-Sign (SFOS) leptons with mass closest to $m_Z$ (91.2 GeV).
    - Require $|m_{\ell\ell} - m_Z| < 10$ GeV.
5.  **W Selection**: The remaining 3rd lepton is the W candidate.
6.  **MET**: $E_T^{miss} > 30$ GeV.
7.  **W Transverse Mass**: $M_T^W > 30$ GeV (using 3rd lepton and MET).

## Expected Output
Return a JSON object with the following structure:
```json
{
  "status": "success",
  "cuts": [ ... ],
  "fit_method": {
    "model": "Cut and Count / W Transverse Mass Reconstruction",
    "reasoning": "Explain Z candidate selection logic and W transverse mass calculation."
  },
  "fit_result": {
    "center": 80.4, # Should report W mass if reconstructing, or Z mass if checking Z. Let's ask for W transverse mass peak or Z mass check.
    # Actually, usually we show the Z peak is clean and W mT is consistent. 
    # Let's ask to report the Z mass of the selected candidate to prove reconstruction.
    "center": 91.2,
    "sigma": 3.0,
    "significance": 5.0
  }
}
```
