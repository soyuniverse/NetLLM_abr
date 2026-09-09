# Serve-time buffer gate -- serve_gate_20260909

A1: QoE 0.94872 / latency 80.63 ms / rebuffer 6.392 s. Criteria T/I/S/Q: dRebuffer <= 0.64s / incidence C <= 0.578% / speedup >= 1.24x / dQoE >= -1.5%.

| phase | drafter | k | gate | floor | trips | QoE | dQoE% | speedup | q | draft 1-step | rebuf (s) | dRebuf | C% | T/I/S/Q | n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| m2_repeat_k3 | repeat-last | 3 | none |  |  | 0.93424 | -1.53 | 1.419x | 37.8% | 87.9% | 23.84 | +17.45 | 0.338 | F/P/P/F | 2 |
| m3_hybrid_k3 | hybrid | 3 | none |  |  | 0.93191 | -1.77 | 1.413x | 37.3% | 83.2% | 26.87 | +20.48 | 0.228 | F/P/P/F | 2 |
| m4_repeat_k5 | repeat-last | 5 | none |  |  | 0.91111 | -3.96 | 1.306x | 41.9% | 87.2% | 37.12 | +30.73 | 0.254 | F/P/P/F | 2 |
| m5_hybrid_k5 | hybrid | 5 | none |  |  | 0.93001 | -1.97 | 1.326x | 41.9% | 82.7% | 18.51 | +12.11 | 0.559 | F/P/P/F | 2 |
| g_hybrid_k3_f5 | hybrid | 3 | fallback | 5.0 |  | 0.91275 | -3.79 | 1.565x | 37.0% | 83.0% | 58.33 | +51.94 |  | F/?/P/F | 1 |
| g_hybrid_k5_f5 | hybrid | 5 | fallback | 5.0 |  | 0.93623 | -1.32 | 1.474x | 41.2% | 83.5% | 7.00 | +0.61 |  | P/?/P/P | 3 |
| g_repeat_k3_f3 | repeat-last | 3 | fallback | 3.0 |  | 0.93424 | -1.53 | 1.565x | 37.8% | 87.9% | 23.84 | +17.45 |  | F/?/P/F | 1 |
| g_repeat_k3_f5 | repeat-last | 3 | fallback | 5.0 |  | 0.91264 | -3.80 | 1.645x | 37.9% | 87.8% | 50.83 | +44.43 |  | F/?/P/F | 1 |
| g_repeat_k3_f5_pred | repeat-last | 3 | fallback | 5.0 |  | 0.91264 | -3.80 | 1.556x | 37.9% | 87.8% | 50.83 | +44.43 |  | F/?/P/F | 1 |
| g_repeat_k3_f8 | repeat-last | 3 | fallback | 8.0 |  | 0.92193 | -2.82 | 1.505x | 34.8% | 88.8% | 50.31 | +43.92 |  | F/?/P/F | 1 |
| g_repeat_k5_f5 | repeat-last | 5 | fallback | 5.0 |  | 0.90011 | -5.12 | 1.488x | 42.1% | 87.9% | 43.02 | +36.63 |  | F/?/P/F | 1 |
| m2_ctrl | repeat-last | 3 | none |  |  | 0.93424 | -1.53 | 1.574x | 37.8% | 87.9% | 23.84 | +17.45 |  | F/?/P/F | 1 |
| m3_ctrl | hybrid | 3 | none |  |  | 0.93191 | -1.77 | 1.662x | 37.3% | 83.2% | 26.87 | +20.48 |  | F/?/P/F | 1 |
| m5_ctrl | hybrid | 5 | none |  |  | 0.93001 | -1.97 | 1.522x | 41.9% | 82.7% | 18.51 | +12.11 |  | F/?/P/F | 1 |
| m5_ctrl_reseed | ? | 3 | none |  |  | 0.94554 | -0.34 | 1.548x | 41.6% | 80.7% | 18.40 | +12.01 |  | F/?/P/P | 2 |
| m5_ctrl_s2 | ? | 3 | none |  |  | 0.95614 | +0.78 | 1.711x | 42.1% | 82.3% | 4.24 | -2.15 | 0.303 | P/P/P/P | 4 |
| m5_ctrl_s3 | ? | 3 | none |  |  | 0.92016 | -3.01 | 1.632x | 42.7% | 84.2% | 25.59 | +19.20 | 0.548 | F/P/P/F | 2 |
| m5_ctrl_s4 | ? | 3 | none |  |  | 0.95283 | +0.43 | 1.587x | 41.1% | 81.3% | 0.48 | -5.91 | 0.052 | P/P/P/P | 4 |
| t_repeat_k3_btol0p5 | repeat-last | 3 | none |  |  | 0.91441 | -3.62 | 1.407x | 31.5% | 87.3% | 32.19 | +25.80 |  | F/?/P/F | 1 |
| v_hybrid_k3_f5_cons | hybrid | 3 | conservative | 5.0 | 2 | 0.91218 | -3.85 | 1.595x | 37.0% | 82.8% | 58.33 | +51.94 |  | F/?/P/F | 1 |
| v_hybrid_k3_f5_safe | hybrid | 3 | safe-mode | 5.0 | 117 | 0.92442 | -2.56 | 1.592x | 36.7% | 85.0% | 25.98 | +19.59 |  | F/?/P/F | 1 |
| v_hybrid_k3_f8_safe | hybrid | 3 | safe-mode | 8.0 | 252 | 0.92945 | -2.03 | 1.611x | 35.3% | 84.6% | 16.59 | +10.20 |  | F/?/P/F | 1 |
| v_hybrid_k5_f3_cons | hybrid | 5 | conservative | 3.0 | 0 | 0.93001 | -1.97 | 1.522x | 41.9% | 82.7% | 18.51 | +12.11 |  | F/?/P/F | 1 |
| v_hybrid_k5_f5_cons | hybrid | 5 | conservative | 5.0 | 3 | 0.94824 | -0.05 | 1.499x | 41.8% | 82.8% | 1.64 | -4.76 |  | P/?/P/P | 3 |
| v_hybrid_k5_f5_cons_reseed | hybrid | 5 | conservative | 5.0 | 1 | 0.94564 | -0.33 | 1.418x | 41.5% | 80.7% | 18.40 | +12.01 |  | F/?/P/P | 2 |
| v_hybrid_k5_f5_cons_s2 | hybrid | 5 | conservative | 5.0 | 2 | 0.95748 | +0.92 | 1.624x | 42.0% | 82.4% | 4.24 | -2.15 | 0.304 | P/P/P/P | 4 |
| v_hybrid_k5_f5_cons_s3 | hybrid | 5 | conservative | 5.0 | 1 | 0.92835 | -2.15 | 1.612x | 41.9% | 83.3% | 29.87 | +23.48 | 0.152 | F/P/P/F | 2 |
| v_hybrid_k5_f5_cons_s4 | hybrid | 5 | conservative | 5.0 | 1 | 0.95363 | +0.52 | 1.577x | 41.0% | 81.7% | 0.48 | -5.91 | 0.052 | P/P/P/P | 4 |
| v_hybrid_k5_f5_fb_s2 | hybrid | 5 | fallback | 5.0 | 2 | 0.95843 | +1.02 | 1.589x | 41.6% | 82.5% | 3.92 | -2.48 | 0.205 | P/P/P/P | 4 |
| v_hybrid_k5_f5_fb_s3 | hybrid | 5 | fallback | 5.0 | 1 | 0.92835 | -2.15 | 1.443x | 42.0% | 83.3% | 29.87 | +23.48 | 0.152 | F/P/P/F | 2 |
| v_hybrid_k5_f5_fb_s4 | hybrid | 5 | fallback | 5.0 | 1 | 0.95353 | +0.51 | 1.387x | 41.0% | 81.6% | 0.48 | -5.91 | 0.052 | P/P/P/P | 4 |
| v_hybrid_k5_f5_safe | hybrid | 5 | safe-mode | 5.0 | 115 | 0.93626 | -1.31 | 1.529x | 41.0% | 84.3% | 39.83 | +33.44 |  | F/?/P/P | 2 |
| v_hybrid_k5_f8_cons | hybrid | 5 | conservative | 8.0 | 45 | 0.93202 | -1.76 | 1.520x | 40.4% | 82.7% | 22.39 | +16.00 |  | F/?/P/F | 1 |
| v_hybrid_k5_f8_safe | hybrid | 5 | safe-mode | 8.0 | 261 | 0.93360 | -1.59 | 1.565x | 39.9% | 84.3% | 41.05 | +34.66 |  | F/?/P/F | 1 |
| v_repeat_k3_f5_cons | repeat-last | 3 | conservative | 5.0 | 4 | 0.93534 | -1.41 | 1.570x | 37.7% | 87.5% | 20.54 | +14.14 |  | F/?/P/P | 2 |
| v_repeat_k3_f5_safe | repeat-last | 3 | safe-mode | 5.0 | 116 | 0.94536 | -0.35 | 1.613x | 37.0% | 88.3% | 19.72 | +13.33 |  | F/?/P/P | 2 |
| v_repeat_k5_f5_cons | repeat-last | 5 | conservative | 5.0 | 2 | 0.91289 | -3.78 | 1.506x | 41.7% | 87.6% | 37.07 | +30.67 |  | F/?/P/F | 1 |
