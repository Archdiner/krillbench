# Outliers to revisit

## Azure content-filter hits (full Azure run, 2026-11-13)

All three were blocks on the model's **reply**, not the prompt. The same prompts passed 35+ other calls.
The current scoring drops any prompt that was filtered for any model, so these 3 prompts are excluded for every model.
To revisit: count only the affected call as missing, and keep the prompt for the other models.

| model | condition | prompt | prompt text |
|---|---|---|---|
| gpt-6-astra | rules-off | 2026-11-07#2 | Name an animated TV show that isn't meant for kids (no anime). |
| kimi-k3.1-pro | rules-high | 2026-11-06#2 | Name a setting you can change in a video game's settings. |
| kimi-k3.1-pro | rules-medium | 2026-10-15#6 | Name an app or service meant for editing photos |

Logging bug: the Kimi hits were labelled "filtered prompt" because Azure returned the reply block as HTTP 400.
