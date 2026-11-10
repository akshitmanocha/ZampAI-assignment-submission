# Indian GST invoice evaluation corpus

Source: [Divya52 / Indian GST invoices](https://huggingface.co/datasets/Divya52/indian-gst-invoices), revision `fece40b9a96ac3949934fc05c714853a5283d730`. Publisher: Divya52. License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This project uses the original synthetic invoice images and structured labels, with no label edits. A neutral image-only PDF wrapper is generated for our PDF reader; this is a format conversion, not a new ground-truth annotation.

`manifest.json` was frozen before scoring. It pins the source metadata, selected record identities, original label strings and image bytes using SHA-256. Original images and publisher metadata download outside Git to `/workspace/reconcile-artifacts/indian-gst-v1` by default. Run `make invoice-data` from the repository root. Re-running preparation verifies the frozen manifest rather than replacing it silently. The evaluator validates source hashes before it starts.

| Suite | Source selection | Count |
|---|---|---:|
| Primary | `synthetic`, metadata `split == test` | 197 |
| Adversarial robustness | All `injection` rows | 24 |
| Regional robustness | All `regional` rows (Hindi/Kannada) | 40 |

The main config has 2,000 records: 1,613 train, 190 validation, 197 test. The Hugging Face loader exposes them together as `train`; the **metadata column** defines the intended splits. Twelve validation images were selected by layout/quality for a potential visibility audit; only the two listed in `validation-audit.json` were visually checked. That agent spot-check is not an independent human audit. No training examples were used to train a reader in this switch.

`split-audit.json` checks source metadata only: no record IDs, exact label strings or supplier/invoice/date identities overlap across splits. All 25 product descriptions occur in every split. This is a held-out invoice split, not an unseen-product-family test; image near-duplicate auditing remains outstanding. Reproduce with `python ml/audit_indian_gst_splits.py`.

Publisher labels are synthetic-generation labels, not annotations produced by Nemotron for this project. Unprinted zero tax components may still appear in the labels; we preserve those values and disclose the visibility limitation. Four layouts and a small recurring source product catalog limit generalization. There are no authoritative PO records, same-product catalog labels, approval outcomes or payment histories.

See [the evaluation report](../../../docs/indian-gst-evaluation.md) for exact scoring rules and limitations. Original published images remain under the publisher's attribution/license terms; application source licensing does not replace those terms.
