# H->yy Analysis Task

## Objective
Perform a Higgs boson to diphoton (H->yy) analysis using ATLAS Open Data (release {{RELEASE}}).

## Requirements

1. **Information Extraction**:
   - Load the `{{SKIM}}` skim data.
   - Process at most {{MAX_FILES}} files (if running in mock mode, use provided mock data).

2. **Event Selection (Cuts)**:
   Apply the following cuts in order:
   - **Photon Reconstruction**: Keep events where both photons pass `tight_id`.
   - **Transverse Momentum**: Leading photon `pt > 50 GeV`, Sub-leading `pt > 30 GeV`.
   - **Isolation**: `ptcone20 / pt < 0.055` for both photons.
   - **Crack Veto**: Exclude photons in the barrel/end-cap transition region `1.37 < |eta| < 1.52`.
   - **Invariant Mass**: Compute `m_yy` from the 4-momenta of the two photons.
   - **Relative pT**: `pt1/m_yy > 0.35` AND `pt2/m_yy > 0.35`.

3. **Statistical Analysis**:
   - Fit the invariant mass spectrum in the range [100, 160] GeV.
   - Signal Model: Gaussian.
   - Background Model: Polynomial (4th order recommended).
   - Report the full `fit_result` including `center` (mu), `sigma`, and `model` description.

4. **Output**:
   - Generate a JSON trace file `submission_trace.json` containing:
     - `task_id`
     - `status`
     - `cuts`: List of cut definitions.
     - `cutflow`: Count of events before/after each cut.
     - `fit_result`: The final fitted parameters.
