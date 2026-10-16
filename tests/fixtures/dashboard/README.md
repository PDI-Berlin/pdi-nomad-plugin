# Original-schema dashboard smoke fixtures

All three test archives use unmodified original NOMAD Material Processing `m_def` definitions.
Their labels and IDs are fictional development-test data. None uses custom PDI schemas.

1. Upload these fixture archives to the **development** NOMAD upload.
2. Confirm `TEST-RECIPE-CLEAN-01` and `TEST-RECIPE-ETCH-01` in Lab Library.
3. Confirm `TEST-HOLDER-01` in New MBE Experiment **after that app has been migrated**
   to the original holder schemas. The old MBE dashboard still queries PDI classes;
   this patch deliberately does not claim that it can yet load original holders.
4. Create crystalline substrates through Substrate Intake (Stage 4), then check the
   native "Substrates" app; it now queries the original CrystallineSubstrate m_def.

No fixture is intended for production. Do not move development data to production.
